from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import secrets
import socket
import time
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import aiohttp
from cryptography.fernet import Fernet, InvalidToken
import msgpack
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from src.config import env, env_int
from src.db.clickhouse.deposit_certificates import COLUMNS, insert_order_books
from src.db.models.parsian import ParsianCredential
from src.db.session import SessionLocal

LOGGER = logging.getLogger(__name__)
TEHRAN = ZoneInfo("Asia/Tehran")
SYMBOLS = frozenset({"GOLDBAR", "GOLDCOIN"})
NEGOTIATE_URL = "https://signal.parsianbroker.com/SignalHub/negotiate?negotiateVersion=1"
HUB_URL = "wss://signal.parsianbroker.com/SignalHub/"
SUBSCRIBE_URL = "https://signal.parsianbroker.com/api/Subscribes/CommoditySubscribe"
UNSUBSCRIBE_URL = "https://signal.parsianbroker.com/api/Subscribes/CommodityUnSubscribe"
SNAPSHOT_URL = "https://gold.parsianbroker.com/api/FeMrkViwMes/GetFeMrkViwMes?market=DepositCertificate"
STREAM_KEY = "stream:parsian:deposit_certificate_orderbook"
GROUP = "clickhouse:deposit_certificate_orderbook"
LISTENER_STATUS_KEY = "status:parsian:listener"
WRITER_STATUS_KEY = "status:parsian:writer"


def normalize_token(raw: str) -> str:
    value = raw.strip()
    if value.startswith('"') and value.endswith('"'):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid quoted token") from exc
        if not isinstance(decoded, str):
            raise ValueError("Token must be text")
        value = decoded.strip()
    if not value or len(value) > 4096 or any(ord(char) < 32 for char in value):
        raise ValueError("Invalid token format")
    if len(value.split(".")) != 5 or any(not part for part in value.split(".")):
        raise ValueError("Expected a five-part JWE token")
    return value


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def _fernet() -> Fernet:
    return Fernet(env("PARSIAN_TOKEN_ENCRYPTION_KEY").encode())


def encryption_key_configured() -> bool:
    try:
        _fernet()
        return True
    except (RuntimeError, ValueError):
        return False


def credential_status() -> dict[str, Any]:
    key_configured = encryption_key_configured()
    with SessionLocal() as session:
        row = session.get(ParsianCredential, 1)
        if not row:
            return {"configured": False, "encryption_key_configured": key_configured}
        return {
            "configured": True,
            "encryption_key_configured": key_configured,
            "fingerprint": row.token_fingerprint,
            "version": row.version,
            "validated_at": row.validated_at,
            "updated_at": row.updated_at,
        }


def load_credential() -> tuple[str, int] | None:
    with SessionLocal() as session:
        row = session.get(ParsianCredential, 1)
        if not row:
            return None
        try:
            token = _fernet().decrypt(row.token_ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Stored Parsian credential cannot be decrypted") from exc
        return token, row.version


def save_credential(token: str) -> None:
    now = datetime.now(timezone.utc)
    ciphertext = _fernet().encrypt(token.encode()).decode()
    with SessionLocal() as session:
        row = session.get(ParsianCredential, 1)
        if row:
            row.token_ciphertext = ciphertext
            row.token_fingerprint = token_fingerprint(token)
            row.version += 1
            row.validated_at = now
            row.updated_at = now
        else:
            session.add(ParsianCredential(
                id=1,
                token_ciphertext=ciphertext,
                token_fingerprint=token_fingerprint(token),
                version=1,
                validated_at=now,
                updated_at=now,
            ))
        session.commit()


def frame_message(payload: bytes) -> bytes:
    length = len(payload)
    prefix = bytearray()
    while True:
        byte = length & 0x7F
        length >>= 7
        prefix.append(byte | (0x80 if length else 0))
        if not length:
            return bytes(prefix) + payload


def split_frames(data: bytes) -> list[bytes]:
    frames: list[bytes] = []
    cursor = 0
    while cursor < len(data):
        size = shift = 0
        for _ in range(5):
            if cursor >= len(data):
                raise ValueError("Incomplete SignalR frame length")
            byte = data[cursor]
            cursor += 1
            size |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7
        else:
            raise ValueError("SignalR frame length is too large")
        end = cursor + size
        if end > len(data):
            raise ValueError("Incomplete SignalR frame")
        frames.append(data[cursor:end])
        cursor = end
    return frames


def _mappings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "ContractSymbol" in value:
            yield value
        else:
            for nested in value.values():
                yield from _mappings(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _mappings(nested)


def decode_updates(data: bytes) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for frame in split_frames(data):
        message = msgpack.unpackb(frame, raw=False, strict_map_key=False)
        if isinstance(message, list) and len(message) >= 5 and message[0] == 1 and message[3] == "CMI":
            updates.extend(item for item in _mappings(message[4]) if item.get("ContractSymbol") in SYMBOLS)
    return updates


def target_symbols(value: Any) -> set[str]:
    return {str(item["ContractSymbol"]) for item in _mappings(value) if item.get("ContractSymbol") in SYMBOLS}


def _parse_provider_time(raw: Any) -> datetime:
    if not isinstance(raw, str) or not raw:
        raise ValueError("Missing provider event time")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TEHRAN)
    return parsed.astimezone(TEHRAN)


def build_snapshot(update: dict[str, Any], received_at: datetime | None = None) -> dict[str, Any]:
    symbol = str(update.get("ContractSymbol", ""))
    if symbol not in SYMBOLS:
        raise ValueError("Unsupported contract symbol")
    provider_at = _parse_provider_time(update.get("LastUpdateDateTime"))
    levels: dict[str, int] = {}
    for side, provider_side in (("bid", "Bid"), ("ask", "Ask")):
        for level in range(1, 4):
            levels[f"{side}_price_{level}"] = int(update.get(f"{provider_side}Price{level}") or 0)
            levels[f"{side}_volume_{level}"] = int(update.get(f"{provider_side}Volume{level}") or 0)
    book_material = json.dumps([symbol, *levels.values()], separators=(",", ":"))
    book_hash = hashlib.sha256(book_material.encode()).hexdigest()
    event_material = f"{book_hash}|{provider_at.isoformat(timespec='milliseconds')}"
    return {
        "event_id": hashlib.sha256(event_material.encode()).hexdigest(),
        "book_hash": book_hash,
        "contract_id": int(update.get("ContractId") or 0),
        "symbol": symbol,
        "provider_event_at": provider_at.isoformat(timespec="milliseconds"),
        "received_at": (received_at or datetime.now(TEHRAN)).astimezone(TEHRAN).isoformat(timespec="milliseconds"),
        **levels,
    }


def should_emit(state: dict[str, str], snapshot: dict[str, Any]) -> bool:
    provider_at = datetime.fromisoformat(snapshot["provider_event_at"])
    old_ms = int(state.get("provider_ms", "0"))
    current_ms = int(provider_at.timestamp() * 1000)
    if old_ms > current_ms:
        return False
    return state.get("book_hash") != snapshot["book_hash"] or state.get("tehran_date") != provider_at.date().isoformat()


async def publish_if_changed(redis: Redis, snapshot: dict[str, Any]) -> bool:
    state_key = f"state:parsian:{snapshot['symbol']}"
    state = await redis.hgetall(state_key)
    if not should_emit(state, snapshot):
        return False
    provider_at = datetime.fromisoformat(snapshot["provider_event_at"])
    payload = json.dumps(snapshot, separators=(",", ":"))
    pipe = redis.pipeline(transaction=True)
    pipe.xadd(STREAM_KEY, {"payload": payload}, maxlen=env_int("PARSIAN_STREAM_MAXLEN"), approximate=True)
    pipe.hset(state_key, mapping={
        "book_hash": snapshot["book_hash"],
        "tehran_date": provider_at.date().isoformat(),
        "provider_ms": str(int(provider_at.timestamp() * 1000)),
    })
    await pipe.execute()
    return True


async def _negotiate(session: aiohttp.ClientSession, token: str) -> dict[str, Any]:
    async with session.post(NEGOTIATE_URL, headers={"Authorization": token}) as response:
        response.raise_for_status()
        result = await response.json()
    if not result.get("connectionId") or not result.get("connectionToken"):
        raise RuntimeError("Parsian negotiate response is incomplete")
    return result


async def _subscribe(session: aiohttp.ClientSession, token: str, connection_id: str, unsubscribe: bool = False) -> None:
    url = UNSUBSCRIBE_URL if unsubscribe else SUBSCRIBE_URL
    async with session.post(
        url,
        headers={"Authorization": token},
        json={"ConnectionId": connection_id, "Market": "DepositCertificate"},
    ) as response:
        response.raise_for_status()


async def _open_feed(session: aiohttp.ClientSession, token: str):
    negotiated = await _negotiate(session, token)
    query = urlencode({"id": negotiated["connectionToken"], "access_token": token})
    ws = await session.ws_connect(f"{HUB_URL}?{query}", autoping=True, heartbeat=20)
    await ws.send_bytes(b'{"protocol":"messagepack","version":1}\x1e')
    handshake = await ws.receive(timeout=10)
    payload = handshake.data
    if handshake.type == aiohttp.WSMsgType.TEXT:
        payload = payload.encode()
    if handshake.type not in {aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY} or not payload.startswith(b"{}\x1e"):
        await ws.close()
        raise RuntimeError("Parsian SignalR handshake failed")
    await _subscribe(session, token, negotiated["connectionId"])
    return ws, negotiated["connectionId"]


async def validate_live_token(token: str, timeout: float = 15.0) -> None:
    found: set[str] = set()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout + 10)) as session:
        ws = connection_id = None
        try:
            ws, connection_id = await _open_feed(session, token)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and found != SYMBOLS:
                try:
                    message = await ws.receive(timeout=max(0.1, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                if message.type == aiohttp.WSMsgType.BINARY:
                    found.update(item["ContractSymbol"] for item in decode_updates(message.data))
                elif message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                    break
            if found != SYMBOLS:
                async with session.get(SNAPSHOT_URL, headers={"Authorization": token}) as response:
                    response.raise_for_status()
                    found.update(target_symbols(await response.json()))
            if found != SYMBOLS:
                raise RuntimeError("Parsian did not provide both target certificates")
        finally:
            if connection_id:
                try:
                    await _subscribe(session, token, connection_id, unsubscribe=True)
                except Exception:
                    pass
            if ws:
                await ws.close()


async def _status(redis: Redis, key: str, **values: Any) -> None:
    mapping = {name: str(value) for name, value in values.items() if value is not None}
    mapping["updated_at"] = datetime.now(TEHRAN).isoformat(timespec="seconds")
    await redis.hset(key, mapping=mapping)


async def stream_status() -> dict[str, Any]:
    redis = Redis.from_url(env("PARSIAN_REDIS_URL"), decode_responses=True)
    try:
        listener, writer, length = await asyncio.gather(
            redis.hgetall(LISTENER_STATUS_KEY), redis.hgetall(WRITER_STATUS_KEY), redis.xlen(STREAM_KEY)
        )
        maximum = env_int("PARSIAN_STREAM_MAXLEN")
        ratio = length / maximum if maximum else 1.0
        return {
            "listener": listener,
            "writer": writer,
            "backlog": length,
            "capacity": maximum,
            "capacity_percent": round(ratio * 100, 2),
            "severity": "critical" if ratio >= 1 else "warning" if ratio >= 0.8 else "ok",
        }
    finally:
        await redis.aclose()


async def _listen_once(redis: Redis, token: str, version: int) -> None:
    timeout = aiohttp.ClientTimeout(total=None, connect=15, sock_connect=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        ws = connection_id = None
        try:
            ws, connection_id = await _open_feed(session, token)
            await _status(redis, LISTENER_STATUS_KEY, state="connected", credential_version=version, error="")
            last_credential_check = last_ping = time.monotonic()
            while True:
                now = time.monotonic()
                if now - last_ping >= 2:
                    await ws.send_bytes(frame_message(msgpack.packb([6], use_bin_type=True)))
                    last_ping = now
                if now - last_credential_check >= 30:
                    current = await asyncio.to_thread(load_credential)
                    if not current or current[1] != version:
                        return
                    last_credential_check = now
                try:
                    message = await ws.receive(timeout=1)
                except asyncio.TimeoutError:
                    continue
                if message.type == aiohttp.WSMsgType.BINARY:
                    updates = decode_updates(message.data)
                    emitted = 0
                    for update in updates:
                        emitted += int(await publish_if_changed(redis, build_snapshot(update)))
                    await _status(
                        redis, LISTENER_STATUS_KEY, state="connected", last_frame_at=datetime.now(TEHRAN).isoformat(),
                        last_frame_symbols=",".join(sorted({u["ContractSymbol"] for u in updates})), last_emitted=emitted,
                    )
                elif message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                    raise ConnectionError("Parsian websocket closed")
        finally:
            if connection_id:
                try:
                    await _subscribe(session, token, connection_id, unsubscribe=True)
                except Exception:
                    pass
            if ws:
                await ws.close()


async def listener_main() -> None:
    logging.basicConfig(level=logging.INFO)
    redis = Redis.from_url(env("PARSIAN_REDIS_URL"), decode_responses=True)
    delay = 1
    try:
        while True:
            try:
                credential = await asyncio.to_thread(load_credential)
                if not credential:
                    await _status(redis, LISTENER_STATUS_KEY, state="credential_required", error="")
                    await asyncio.sleep(10)
                    continue
                await _listen_once(redis, *credential)
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("Parsian listener reconnecting after %s", type(exc).__name__)
                await _status(redis, LISTENER_STATUS_KEY, state="reconnecting", error=type(exc).__name__)
                await asyncio.sleep(delay + secrets.randbelow(1000) / 1000)
                delay = min(delay * 2, 30)
    finally:
        await redis.aclose()


def _writer_row(message_id: str, payload: str) -> dict[str, Any]:
    row = json.loads(payload)
    row["redis_id"] = message_id
    row["provider_event_at"] = datetime.fromisoformat(row["provider_event_at"])
    row["received_at"] = datetime.fromisoformat(row["received_at"])
    return {column: row[column] for column in COLUMNS}


async def _write_messages(redis: Redis, messages: list[tuple[str, dict[str, str]]]) -> None:
    valid: list[tuple[str, dict[str, Any]]] = []
    invalid: list[str] = []
    for message_id, fields in messages:
        try:
            valid.append((message_id, _writer_row(message_id, fields["payload"])))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            invalid.append(message_id)
    if valid:
        await asyncio.to_thread(insert_order_books, [row for _, row in valid])
        ids = [message_id for message_id, _ in valid]
        await redis.xack(STREAM_KEY, GROUP, *ids)
        await redis.xdel(STREAM_KEY, *ids)
    if invalid:
        await redis.xack(STREAM_KEY, GROUP, *invalid)
        await redis.xdel(STREAM_KEY, *invalid)
        await _status(redis, WRITER_STATUS_KEY, error="malformed_stream_entry")


async def writer_main() -> None:
    logging.basicConfig(level=logging.INFO)
    redis = Redis.from_url(env("PARSIAN_REDIS_URL"), decode_responses=True)
    consumer = f"{socket.gethostname()}-{secrets.token_hex(4)}"
    try:
        try:
            await redis.xgroup_create(STREAM_KEY, GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        while True:
            try:
                claimed = await redis.xautoclaim(STREAM_KEY, GROUP, consumer, min_idle_time=60_000, start_id="0-0", count=500)
                if claimed[1]:
                    await _write_messages(redis, claimed[1])
                    continue
                batches = await redis.xreadgroup(GROUP, consumer, {STREAM_KEY: ">"}, count=500, block=1000)
                if batches:
                    await _write_messages(redis, batches[0][1])
                    await _status(
                        redis, WRITER_STATUS_KEY, state="running", last_write_at=datetime.now(TEHRAN).isoformat(), error=""
                    )
                else:
                    await _status(redis, WRITER_STATUS_KEY, state="running", error="")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("Parsian writer retrying after %s", type(exc).__name__)
                await _status(redis, WRITER_STATUS_KEY, state="retrying", error=type(exc).__name__)
                await asyncio.sleep(2)
    finally:
        await redis.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=("listener", "writer"))
    service = parser.parse_args().service
    asyncio.run(listener_main() if service == "listener" else writer_main())


if __name__ == "__main__":
    main()
