from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.bond.trade_fetcher import (
    backfill_trades,
    fetch_trades_for_date,
    get_active_instrument_codes,
)


class TestGetActiveInstrumentCodes:
    @patch("src.collectors.bond.order_book_fetcher.SessionLocal")
    async def test_returns_active_codes(self, mock_session_local: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = [
            ("code1",),
            ("code2",),
        ]

        codes = await get_active_instrument_codes()
        assert codes == ["code1", "code2"]

    @patch("src.collectors.bond.order_book_fetcher.SessionLocal")
    async def test_empty(self, mock_session_local: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = []

        codes = await get_active_instrument_codes()
        assert codes == []


class TestFetchTradesForDate:
    @pytest.fixture
    def mock_client(self) -> MagicMock:
        from src.collectors.bond.models import TradeEntry

        client = AsyncMock()
        client.get_trade_history.return_value = [
            TradeEntry(
                h_even=60123,
                n_tran=1001,
                price=821980.0,
                volume=50,
                canceled=False,
            ),
        ]
        return client

    @patch("src.collectors.bond.trade_fetcher.insert_trades")
    async def test_inserts_rows(
        self, mock_insert: MagicMock, mock_client: MagicMock
    ) -> None:
        result = await fetch_trades_for_date(
            client=mock_client,
            instrument_code="36408112396351116",
            trade_date=date(2026, 6, 10),
        )
        assert result == 1
        mock_insert.assert_called_once()
        args = mock_insert.call_args[0][0]
        assert len(args) == 1
        assert args[0]["instrument_code"] == "36408112396351116"

    @patch("src.collectors.bond.trade_fetcher.insert_trades")
    async def test_no_trades_no_insert(
        self, mock_insert: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.get_trade_history.return_value = []
        result = await fetch_trades_for_date(
            client=mock_client,
            instrument_code="code",
            trade_date=date(2026, 6, 10),
        )
        assert result == 0
        mock_insert.assert_not_called()


class TestBackfillTrades:
    @patch("src.collectors.bond.trade_fetcher.get_active_instrument_codes")
    @patch("src.collectors.bond.trade_fetcher.insert_trades")
    async def test_backfill_with_explicit_codes(
        self, mock_insert: MagicMock, mock_get_codes: MagicMock
    ) -> None:
        from src.collectors.bond.models import TradeEntry

        items_per_request: list[list] = [
            [
                TradeEntry(60123, 1001, 821980.0, 50, False),
                TradeEntry(60124, 1002, 822000.0, 30, False),
            ],
            [],
        ]

        call_count = 0

        async def get_trade_history(
            code: str, trade_date: date
        ) -> list:
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
            "src.collectors.bond.trade_fetcher.TsetmcClient", mock_client_cls
        ):
            result = await backfill_trades(
                start_date=date(2026, 6, 10),
                end_date=date(2026, 6, 10),
                instrument_codes=["code1", "code2"],
            )

        assert result["total_days_tried"] == 2
        assert result["total_rows"] == 2
        assert result["errors"] == []
        mock_get_codes.assert_not_called()

    @patch("src.collectors.bond.trade_fetcher.get_active_instrument_codes")
    @patch("src.collectors.bond.trade_fetcher.insert_trades")
    async def test_backfill_reads_from_pg(
        self, mock_insert: MagicMock, mock_get_codes: MagicMock
    ) -> None:
        mock_get_codes.return_value = ["code1"]

        mock_client_cls = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.get_trade_history.return_value = []
        mock_client_cls.return_value.__aenter__.return_value = mock_client_instance

        with patch(
            "src.collectors.bond.trade_fetcher.TsetmcClient", mock_client_cls
        ):
            result = await backfill_trades(
                start_date=date(2026, 6, 10),
                end_date=date(2026, 6, 11),
            )

        assert result["total_days_tried"] == 2
        mock_get_codes.assert_called_once()

    @patch("src.collectors.bond.trade_fetcher.get_active_instrument_codes")
    @patch("src.collectors.bond.trade_fetcher.insert_trades")
    async def test_backfill_errors(
        self, mock_insert: MagicMock, mock_get_codes: MagicMock
    ) -> None:
        mock_get_codes.return_value = ["code1"]

        mock_client_cls = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.get_trade_history.side_effect = ValueError("boom")
        mock_client_cls.return_value.__aenter__.return_value = mock_client_instance

        with patch(
            "src.collectors.bond.trade_fetcher.TsetmcClient", mock_client_cls
        ):
            result = await backfill_trades(
                start_date=date(2026, 6, 10),
                end_date=date(2026, 6, 10),
            )

        assert result["total_days_tried"] == 0
        assert result["total_rows"] == 0
        assert len(result["errors"]) == 1
        assert "boom" in result["errors"][0]
