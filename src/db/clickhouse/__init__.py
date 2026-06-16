import os
import time

import clickhouse_connect
from clickhouse_connect.driver import Client
from clickhouse_connect.driver.asyncclient import AsyncClient

_client: Client | None = None
_async_client: AsyncClient | None = None
_RETRIES = 3
_RETRY_DELAY = 1.0


def get_client() -> Client:
    global _client
    if _client is not None:
        try:
            _client.command("SELECT 1")
            return _client
        except Exception:
            _client = None

    last_exc: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            _client = clickhouse_connect.get_client(
                host=os.getenv("CLICKHOUSE_HOST", "localhost"),
                port=int(os.getenv("CLICKHOUSE_PORT", "9000")),
                username=os.getenv("CLICKHOUSE_USER", "default"),
                password=os.getenv("CLICKHOUSE_PASSWORD", ""),
                connect_timeout=10,
            )
            _client.command("SELECT 1")
            return _client
        except Exception as e:
            last_exc = e
            if attempt < _RETRIES - 1:
                time.sleep(_RETRY_DELAY * (attempt + 1))

    raise ConnectionError(
        f"Cannot connect to ClickHouse after {_RETRIES} attempts"
    ) from last_exc


async def get_async_client() -> AsyncClient:
    global _async_client
    if _async_client is not None:
        try:
            await _async_client.query("SELECT 1")
            return _async_client
        except Exception:
            _async_client = None

    last_exc: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            _async_client = await clickhouse_connect.get_async_client(
                host=os.getenv("CLICKHOUSE_HOST", "localhost"),
                port=int(os.getenv("CLICKHOUSE_PORT", "9000")),
                username=os.getenv("CLICKHOUSE_USER", "default"),
                password=os.getenv("CLICKHOUSE_PASSWORD", ""),
                connect_timeout=10,
            )
            await _async_client.query("SELECT 1")
            return _async_client
        except Exception as e:
            last_exc = e
            if attempt < _RETRIES - 1:
                await _async_sleep(_RETRY_DELAY * (attempt + 1))

    raise ConnectionError(
        f"Cannot connect to ClickHouse after {_RETRIES} attempts"
    ) from last_exc


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


def _ensure_client(client: Client | None) -> Client:
    return client if client is not None else get_client()


def price_to_storage(price: float | int) -> int:
    return int(price)


def price_from_storage(price: int) -> float:
    return float(price)