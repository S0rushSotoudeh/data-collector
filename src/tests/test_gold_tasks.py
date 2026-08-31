from datetime import date
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from src.collectors.stock.order_book_fetcher import (
    get_active_gold_etf_codes,
    get_gold_etf_codes_active_in_range,
)
from src.tasks import (
    backfill_gold_order_books_task,
    backfill_gold_trades_task,
    fetch_yesterday_gold_orderbook,
    fetch_yesterday_gold_trades,
)


class TestGoldEtfQueries:
    @pytest.mark.asyncio
    @patch("src.collectors.stock.order_book_fetcher.SessionLocal")
    async def test_get_active_gold_etf_codes(self, mock_session_local: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = [
            ("gold1",),
            ("gold2",),
        ]

        codes = await get_active_gold_etf_codes()
        assert codes == ["gold1", "gold2"]

    @pytest.mark.asyncio
    @patch("src.collectors.stock.order_book_fetcher.SessionLocal")
    async def test_get_gold_etf_codes_active_in_range(self, mock_session_local: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = [
            ("gold1",),
        ]

        codes = await get_gold_etf_codes_active_in_range(date(2026, 8, 1), date(2026, 8, 10))
        assert codes == ["gold1"]


class TestGoldBackfillTasks:
    def test_backfill_gold_order_books_task(self) -> None:
        expected = {"total_rows": 45, "errors": []}
        collector = AsyncMock(return_value=expected)
        get_codes = AsyncMock(return_value=["gold1", "gold2"])

        with patch("src.tasks.get_gold_etf_codes_active_in_range", get_codes), \
             patch("src.tasks.backfill_stock_order_books", collector):
            result = backfill_gold_order_books_task.run("2026-08-01", "2026-08-05")

        assert result["total_rows"] == 45
        assert result["instrument_count"] == 2
        collector.assert_awaited_once_with(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 5),
            instrument_codes=["gold1", "gold2"],
            progress=ANY,
        )

    def test_backfill_gold_trades_task(self) -> None:
        expected = {"total_rows": 100, "skipped": 0, "errors": []}
        collector = AsyncMock(return_value=expected)
        get_codes = AsyncMock(return_value=["gold1"])

        with patch("src.tasks.get_gold_etf_codes_active_in_range", get_codes), \
             patch("src.tasks.backfill_stock_trades", collector):
            result = backfill_gold_trades_task.run("2026-08-01", "2026-08-05")

        assert result["total_rows"] == 100
        assert result["instrument_count"] == 1
        collector.assert_awaited_once_with(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 5),
            instrument_codes=["gold1"],
            progress=ANY,
        )

    def test_fetch_yesterday_gold_orderbook(self) -> None:
        expected = {"total_rows": 20, "errors": []}
        collector = AsyncMock(return_value=expected)
        get_codes = AsyncMock(return_value=["gold1"])

        with patch("src.tasks.get_gold_etf_codes_active_in_range", get_codes), \
             patch("src.tasks.backfill_stock_order_books", collector):
            result = fetch_yesterday_gold_orderbook.run()

        assert result["total_rows"] == 20
        assert result["instrument_count"] == 1

    def test_fetch_yesterday_gold_trades(self) -> None:
        expected = {"total_rows": 30, "skipped": 0, "errors": []}
        collector = AsyncMock(return_value=expected)
        get_codes = AsyncMock(return_value=["gold1"])

        with patch("src.tasks.get_gold_etf_codes_active_in_range", get_codes), \
             patch("src.tasks.backfill_stock_trades", collector):
            result = fetch_yesterday_gold_trades.run()

        assert result["total_rows"] == 30
        assert result["instrument_count"] == 1
