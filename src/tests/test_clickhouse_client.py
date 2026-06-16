from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.clickhouse import get_client
from src.db.clickhouse import get_async_client


class TestGetClient:
    def test_successful_connection(self, reset_client_cache) -> None:
        with patch("src.db.clickhouse.clickhouse_connect.get_client") as m:
            instance = MagicMock()
            instance.command.return_value = None
            m.return_value = instance

            client = get_client()

            assert client is instance
            instance.command.assert_called_once_with("SELECT 1")

    def test_health_check_fails_then_reconnects(self, reset_client_cache) -> None:
        with patch("src.db.clickhouse.clickhouse_connect.get_client") as m:
            first = MagicMock()
            first.command.side_effect = RuntimeError("Connection lost")
            second = MagicMock()
            second.command.return_value = None
            m.side_effect = [first, second]

            _client = get_client()

            assert _client is second
            assert m.call_count == 2

    def test_all_retries_fail_raises(self, reset_client_cache) -> None:
        with patch("src.db.clickhouse.clickhouse_connect.get_client") as m:
            instance = MagicMock()
            instance.command.side_effect = RuntimeError("Down")
            m.return_value = instance

            with pytest.raises(ConnectionError):
                get_client()

    def test_cached_client_skips_reconnect(self, reset_client_cache) -> None:
        with patch("src.db.clickhouse.clickhouse_connect.get_client") as m:
            instance = MagicMock()
            instance.command.return_value = None
            m.return_value = instance

            first = get_client()
            second = get_client()

            assert first is second
            assert m.call_count == 1

    def test_stale_client_reconnects(self, reset_client_cache) -> None:
        with patch("src.db.clickhouse.clickhouse_connect.get_client") as m:
            first = MagicMock()
            first.command.side_effect = RuntimeError("Stale")
            second = MagicMock()
            second.command.return_value = None
            m.side_effect = [first, second]

            _client = get_client()

            assert _client is second


class TestGetAsyncClient:
    async def test_successful_connection(self, reset_client_cache) -> None:
        with patch("src.db.clickhouse.clickhouse_connect.get_async_client") as m:
            instance = AsyncMock()
            instance.query = AsyncMock()
            m.return_value = instance

            client = await get_async_client()

            assert client is instance

    async def test_async_all_retries_fail_raises(self, reset_client_cache) -> None:
        with patch("src.db.clickhouse.clickhouse_connect.get_async_client") as m:
            instance = AsyncMock()
            instance.query.side_effect = RuntimeError("Down")
            m.return_value = instance

            with pytest.raises(ConnectionError):
                await get_async_client()

    async def test_async_cached_client_used(self, reset_client_cache) -> None:
        with patch("src.db.clickhouse.clickhouse_connect.get_async_client") as m:
            instance = AsyncMock()
            instance.query = AsyncMock()
            m.return_value = instance

            first = await get_async_client()
            second = await get_async_client()

            assert first is second
            assert m.call_count == 1