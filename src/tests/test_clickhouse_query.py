from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.db.clickhouse.query import (
    get_vwap,
    get_ohlcv,
    get_latest_trades,
    get_latest_order_book,
    get_order_book_history,
    get_trade_history,
    get_daily_spread,
)


class TestOrderBook:
    async def test_get_latest_order_book(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [
            ("code", date(2026, 6, 16), 90000, 1, 1, 842190, 100, 5, 842200, 200, 3, "rest", "2026-06-16")
        ]
        result = await get_latest_order_book("code", date(2026, 6, 16))
        assert len(result) == 1
        assert result[0]["bid_price"] == 842190.0
        assert result[0]["ask_price"] == 842200.0

    async def test_empty_result(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = []
        result = await get_latest_order_book("code", date(2026, 6, 16))
        assert result == []


class TestTrades:
    async def test_get_trade_history(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [
            ("code", date(2026, 6, 16), 90000, 1, 842190, 100, 84219000, 0, "rest", "2026-06-16")
        ]
        result = await get_trade_history("code", date(2026, 6, 16))
        assert len(result) == 1
        assert result[0]["price"] == 842190.0
        assert result[0]["value"] == 84219000.0


class TestVWAP:
    async def test_get_vwap(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [(850000, 500, 425000000, 10)]
        result = await get_vwap("code", date(2026, 6, 16))
        assert result is not None
        assert result["vwap"] == 850000.0
        assert result["total_volume"] == 500
        assert result["trade_count"] == 10

    async def test_get_vwap_no_data(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [(None, None, None, None)]
        result = await get_vwap("code", date(2026, 6, 16))
        assert result is None

    async def test_get_vwap_empty(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = []
        result = await get_vwap("code", date(2026, 6, 16))
        assert result is None


class TestOHLCV:
    async def test_get_ohlcv(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [
            (9, 840000, 850000, 838000, 848000, 1000, 844000)
        ]
        result = await get_ohlcv("code", date(2026, 6, 16))
        assert len(result) == 1
        assert result[0]["hour"] == 9
        assert result[0]["open"] == 840000.0
        assert result[0]["high"] == 850000.0
        assert result[0]["low"] == 838000.0
        assert result[0]["close"] == 848000.0
        assert result[0]["volume"] == 1000

    async def test_get_ohlcv_empty(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = []
        result = await get_ohlcv("code", date(2026, 6, 16))
        assert result == []


class TestDailySpread:
    async def test_get_daily_spread(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [(100, 500, 250)]
        result = await get_daily_spread("code", date(2026, 6, 16))
        assert result == {"min_spread": 100.0, "max_spread": 500.0, "avg_spread": 250.0}

    async def test_get_daily_spread_no_data(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [(None, None, None)]
        result = await get_daily_spread("code", date(2026, 6, 16))
        assert result is None


class TestLatestTrades:
    async def test_get_latest_trades(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [
            ("code", date(2026, 6, 16), 90000, 1, 842190, 100, 84219000, 0, "rest", "2026-06-16")
        ]
        result = await get_latest_trades(limit=5)
        assert len(result) == 1
        assert result[0]["price"] == 842190.0