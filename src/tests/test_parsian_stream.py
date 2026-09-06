from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.fernet import Fernet
import msgpack
import pytest

from src.collectors.parsian_stream import (
    build_snapshot, decode_updates, encryption_key_configured, frame_message, load_credential, normalize_token,
    publish_if_changed, save_credential, should_emit, split_frames, target_symbols,
)


def update(symbol="GOLDBAR", price=100):
    row = {"ContractId": 41, "ContractSymbol": symbol, "LastUpdateDateTime": "2026-09-05T10:00:00+03:30"}
    for side in ("Bid", "Ask"):
        for level in range(1, 4):
            row[f"{side}Price{level}"] = price + level
            row[f"{side}Volume{level}"] = level * 10
    return row


def test_signalr_messagepack_frames_and_target_filter():
    message = [1, {}, None, "CMI", [[update(), update("OTHER")]], []]
    framed = frame_message(msgpack.packb(message, use_bin_type=True))
    assert split_frames(framed) == [msgpack.packb(message, use_bin_type=True)]
    assert [row["ContractSymbol"] for row in decode_updates(framed)] == ["GOLDBAR"]
    with pytest.raises(ValueError, match="Incomplete"):
        split_frames(framed[:-1])
    assert target_symbols([update(), update("GOLDCOIN"), update("OTHER")]) == {"GOLDBAR", "GOLDCOIN"}


def test_change_detection_ignores_heartbeat_and_emits_daily_baseline():
    first = build_snapshot(update(), datetime.fromisoformat("2026-09-05T10:00:01+03:30"))
    heartbeat = build_snapshot({**update(), "LastUpdateDateTime": "2026-09-05T10:00:02+03:30"})
    state = {
        "book_hash": first["book_hash"], "tehran_date": "2026-09-05",
        "provider_ms": str(int(datetime.fromisoformat(first["provider_event_at"]).timestamp() * 1000)),
    }
    assert should_emit(state, heartbeat) is False
    assert should_emit({**state, "tehran_date": "2026-09-04"}, first) is True
    assert should_emit(state, build_snapshot(update(price=101))) is True
    older = build_snapshot({**update(price=101), "LastUpdateDateTime": "2026-09-05T09:59:59+03:30"})
    assert should_emit(state, older) is False


@pytest.mark.asyncio
async def test_publish_updates_state_and_stream_atomically(monkeypatch):
    monkeypatch.setenv("PARSIAN_STREAM_MAXLEN", "100")
    redis = MagicMock()
    redis.hgetall = AsyncMock(return_value={})
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    redis.pipeline.return_value = pipe
    snapshot = build_snapshot(update())
    assert await publish_if_changed(redis, snapshot) is True
    pipe.xadd.assert_called_once()
    pipe.hset.assert_called_once()
    pipe.execute.assert_awaited_once()


def test_token_normalization_accepts_local_storage_json_and_rejects_non_jwe():
    token = ".".join(["part"] * 5)
    assert normalize_token(f'"{token}"') == token
    with pytest.raises(ValueError, match="five-part"):
        normalize_token("not-a-jwe")


def test_saved_credential_is_encrypted_and_loadable(monkeypatch):
    monkeypatch.setenv("PARSIAN_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = ".".join(["secret"] * 5)
    session = MagicMock()
    session.get.return_value = None
    context = MagicMock()
    context.__enter__.return_value = session
    with patch("src.collectors.parsian_stream.SessionLocal", return_value=context):
        save_credential(token)
    row = session.add.call_args.args[0]
    assert token not in row.token_ciphertext

    load_session = MagicMock()
    load_session.get.return_value = row
    load_context = MagicMock()
    load_context.__enter__.return_value = load_session
    with patch("src.collectors.parsian_stream.SessionLocal", return_value=load_context):
        assert load_credential() == (token, 1)


def test_encryption_key_status_is_safe(monkeypatch):
    monkeypatch.delenv("PARSIAN_TOKEN_ENCRYPTION_KEY", raising=False)
    assert encryption_key_configured() is False
    monkeypatch.setenv("PARSIAN_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert encryption_key_configured() is True
