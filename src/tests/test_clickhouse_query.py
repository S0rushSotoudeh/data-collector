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
    get_yield_curve_fits_paginated,
    count_yield_curve_fits,
    get_yield_curve_bonds_paginated,
    count_yield_curve_bonds,
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


class TestYieldCurveFits:
    _YCF_ROW = (
        date(2026, 6, 16), 34200, "bid",
        0.08, 0.02, 0.01, 1.5, 0.003, 5, 8, 1, "", "2026-06-16 09:30:00.000",
    )

    async def test_paginated_with_filters(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [self._YCF_ROW]
        result = await get_yield_curve_fits_paginated(
            trade_date=date(2026, 6, 16),
            curve_side="bid",
            converged=1,
            offset=0,
            limit=100,
        )
        assert len(result) == 1
        assert result[0]["trade_date"] == date(2026, 6, 16)
        assert result[0]["curve_side"] == "bid"
        assert result[0]["converged"] == 1

    async def test_paginated_without_filters(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [self._YCF_ROW]
        result = await get_yield_curve_fits_paginated()
        assert len(result) == 1

    async def test_paginated_empty(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = []
        result = await get_yield_curve_fits_paginated(
            trade_date=date(2026, 6, 16),
        )
        assert result == []

    async def test_count_with_filters(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [(3,)]
        total = await count_yield_curve_fits(
            trade_date=date(2026, 6, 16),
            curve_side="bid",
            converged=1,
        )
        assert total == 3

    async def test_count_without_filters(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [(10,)]
        total = await count_yield_curve_fits()
        assert total == 10

    async def test_count_empty(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = []
        total = await count_yield_curve_fits(trade_date=date(2026, 6, 16))
        assert total == 0

    async def test_converged_zero_retained(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [(2,)]
        total = await count_yield_curve_fits(
            trade_date=date(2026, 6, 16),
            converged=0,
        )
        assert total == 2
        call_kwargs = mock_async_client.query.call_args[1]
        assert "conv" in call_kwargs["parameters"]


class TestYieldCurveBonds:
    _YCB_ROW = (
        date(2026, 6, 16), 34200, "inst1", "bid", "اخزا",
        2.5, 950000, 100, 0.18, 0.19, 100.0, "2026-06-16 09:30:00.000",
    )

    async def test_paginated_with_filters(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [self._YCB_ROW]
        result = await get_yield_curve_bonds_paginated(
            trade_date=date(2026, 6, 16),
            trade_time=34200,
            instrument_code="inst1",
            curve_side="bid",
            symbol="اخزا",
            offset=0,
            limit=100,
        )
        assert len(result) == 1
        assert result[0]["trade_date"] == date(2026, 6, 16)
        assert result[0]["instrument_code"] == "inst1"
        assert result[0]["curve_side"] == "bid"

    async def test_paginated_without_filters(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [self._YCB_ROW]
        result = await get_yield_curve_bonds_paginated()
        assert len(result) == 1

    async def test_paginated_empty(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = []
        result = await get_yield_curve_bonds_paginated(
            trade_date=date(2026, 6, 16),
        )
        assert result == []

    async def test_count_with_filters(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [(5,)]
        total = await count_yield_curve_bonds(
            trade_date=date(2026, 6, 16),
            trade_time=34200,
            instrument_code="inst1",
            curve_side="bid",
        )
        assert total == 5

    async def test_count_without_filters(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = [(20,)]
        total = await count_yield_curve_bonds()
        assert total == 20

    async def test_count_empty(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.query.return_value.result_rows = []
        total = await count_yield_curve_bonds(trade_date=date(2026, 6, 16))
        assert total == 0
