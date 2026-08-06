from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.stock.order_book_fetcher import (
    backfill_stock_order_books,
    fetch_stock_order_book_for_date,
    get_active_stock_codes,
)


class TestGetActiveStockCodes:
    @patch("src.collectors.stock.order_book_fetcher.SessionLocal")
    async def test_returns_active_codes(self, mock_session_local: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = [
            ("code1",),
            ("code2",),
        ]

        codes = await get_active_stock_codes()
        assert codes == ["code1", "code2"]

    @patch("src.collectors.stock.order_book_fetcher.SessionLocal")
    async def test_empty(self, mock_session_local: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = []

        codes = await get_active_stock_codes()
        assert codes == []


class TestFetchStockOrderBookForDate:
    @pytest.fixture
    def mock_client(self) -> MagicMock:
        from src.collectors.stock.models import BestLimitEntry

        client = AsyncMock()
        client.get_best_limits.return_value = [
            BestLimitEntry(
                h_even=60123,
                ref_id=15174976313,
                depth_level=1,
                bid_price=24000.0,
                bid_volume=1000,
                bid_order_count=5,
                ask_price=24500.0,
                ask_volume=790,
                ask_order_count=3,
            ),
        ]
        return client

    @patch("src.collectors.stock.order_book_fetcher.insert_stock_order_book")
    async def test_inserts_rows(
        self, mock_insert: MagicMock, mock_client: MagicMock
    ) -> None:
        result = await fetch_stock_order_book_for_date(
            client=mock_client,
            instrument_code="35100368959864864",
            trade_date=date(2026, 7, 1),
        )
        assert result == 1
        mock_insert.assert_called_once()
        args = mock_insert.call_args[0][0]
        assert len(args) == 1
        assert args[0]["instrument_code"] == "35100368959864864"

    @patch("src.collectors.stock.order_book_fetcher.insert_stock_order_book")
    async def test_no_limits_no_insert(
        self, mock_insert: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.get_best_limits.return_value = []
        result = await fetch_stock_order_book_for_date(
            client=mock_client,
            instrument_code="code",
            trade_date=date(2026, 7, 1),
        )
        assert result == 0
        mock_insert.assert_not_called()


class TestBackfillStockOrderBooks:
    @patch("src.collectors.stock.order_book_fetcher.get_active_stock_codes")
    @patch("src.collectors.stock.order_book_fetcher.insert_stock_order_book")
    async def test_backfill_with_explicit_codes(
        self, mock_insert: MagicMock, mock_get_codes: MagicMock
    ) -> None:
        from src.collectors.stock.models import BestLimitEntry

        items_per_request: list[list] = [
            [
                BestLimitEntry(60123, 1, 1, 24000.0, 1000, 5, 24500.0, 790, 3),
                BestLimitEntry(60123, 1, 2, 23900.0, 500, 2, 24600.0, 300, 1),
            ],
            [],
        ]

        call_count = 0

        async def get_best_limits(code: str, trade_date: date) -> list:
            nonlocal call_count
            if call_count < len(items_per_request):
                result = items_per_request[call_count]
                call_count += 1
                return result
            return []

        mock_client_cls = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.get_best_limits = get_best_limits
        mock_client_cls.return_value.__aenter__.return_value = mock_client_instance

        with patch(
            "src.collectors.stock.order_book_fetcher.StockTsetmcClient", mock_client_cls
        ):
            result = await backfill_stock_order_books(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 1),
                instrument_codes=["code1", "code2"],
            )

        assert result["total_days_tried"] == 2
        assert result["total_rows"] == 2
        assert result["errors"] == []
        mock_get_codes.assert_not_called()

    @patch("src.collectors.stock.order_book_fetcher.get_active_stock_codes")
    @patch("src.collectors.stock.order_book_fetcher.insert_stock_order_book")
    async def test_backfill_errors(
        self, mock_insert: MagicMock, mock_get_codes: MagicMock
    ) -> None:
        mock_get_codes.return_value = ["code1"]

        mock_client_cls = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.get_best_limits.side_effect = ValueError("boom")
        mock_client_cls.return_value.__aenter__.return_value = mock_client_instance

        with patch(
            "src.collectors.stock.order_book_fetcher.StockTsetmcClient", mock_client_cls
        ):
            result = await backfill_stock_order_books(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 1),
            )

        assert result["total_days_tried"] == 0
        assert result["total_rows"] == 0
        assert len(result["errors"]) == 1
        assert "boom" in result["errors"][0]
