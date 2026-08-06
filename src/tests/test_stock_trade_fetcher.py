from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.stock.trade_fetcher import (
    backfill_stock_trades,
    fetch_stock_trades_for_date,
)


class TestFetchStockTradesForDate:
    @pytest.fixture
    def mock_client(self) -> MagicMock:
        from src.collectors.stock.models import TradeEntry

        client = AsyncMock()
        client.get_trade_history.return_value = [
            TradeEntry(
                h_even=60123,
                n_tran=1001,
                price=24250.0,
                volume=100,
                canceled=False,
            ),
        ]
        return client

    @patch("src.collectors.stock.trade_fetcher.insert_stock_trades")
    async def test_inserts_rows(
        self, mock_insert: MagicMock, mock_client: MagicMock
    ) -> None:
        result = await fetch_stock_trades_for_date(
            client=mock_client,
            instrument_code="35100368959864864",
            trade_date=date(2026, 7, 1),
        )
        assert result == 1
        mock_insert.assert_called_once()
        args = mock_insert.call_args[0][0]
        assert len(args) == 1
        assert args[0]["instrument_code"] == "35100368959864864"

    @patch("src.collectors.stock.trade_fetcher.insert_stock_trades")
    async def test_no_trades_no_insert(
        self, mock_insert: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.get_trade_history.return_value = []
        result = await fetch_stock_trades_for_date(
            client=mock_client,
            instrument_code="code",
            trade_date=date(2026, 7, 1),
        )
        assert result == 0
        mock_insert.assert_not_called()


class TestBackfillStockTrades:
    @patch("src.collectors.stock.trade_fetcher.get_active_stock_codes")
    @patch("src.collectors.stock.trade_fetcher.insert_stock_trades")
    @patch("src.collectors.stock.trade_fetcher._has_existing_stock_trades")
    async def test_backfill_with_explicit_codes(
        self, mock_has: MagicMock, mock_insert: MagicMock, mock_get_codes: MagicMock
    ) -> None:
        from src.collectors.stock.models import TradeEntry

        mock_has.return_value = False
        items_per_request: list[list] = [
            [
                TradeEntry(60123, 1001, 24250.0, 100, False),
                TradeEntry(60124, 1002, 24300.0, 30, False),
            ],
            [],
        ]

        call_count = 0

        async def get_trade_history(code: str, trade_date: date) -> list:
            nonlocal call_count
            if call_count < len(items_per_request):
                result = items_per_request[call_count]
                call_count += 1
                return result
            return []

        mock_client_cls = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.get_trade_history = get_trade_history
        mock_client_cls.return_value.__aenter__.return_value = mock_client_instance

        with patch(
            "src.collectors.stock.trade_fetcher.StockTsetmcClient", mock_client_cls
        ):
            result = await backfill_stock_trades(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 1),
                instrument_codes=["code1", "code2"],
            )

        assert result["total_days_tried"] == 2
        assert result["total_rows"] == 2
        assert result["errors"] == []
        mock_get_codes.assert_not_called()

    @patch("src.collectors.stock.trade_fetcher.get_active_stock_codes")
    @patch("src.collectors.stock.trade_fetcher.insert_stock_trades")
    @patch("src.collectors.stock.trade_fetcher._has_existing_stock_trades")
    async def test_backfill_skips_existing(
        self, mock_has: MagicMock, mock_insert: MagicMock, mock_get_codes: MagicMock
    ) -> None:
        mock_get_codes.return_value = ["code1"]
        mock_has.return_value = True

        mock_client_cls = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.get_trade_history.return_value = []
        mock_client_cls.return_value.__aenter__.return_value = mock_client_instance

        with patch(
            "src.collectors.stock.trade_fetcher.StockTsetmcClient", mock_client_cls
        ):
            result = await backfill_stock_trades(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 1),
            )

        assert result["total_days_tried"] == 0
        assert result["skipped"] == 1
        assert result["total_rows"] == 0
