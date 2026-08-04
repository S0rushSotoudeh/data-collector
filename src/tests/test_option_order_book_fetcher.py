from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.option.order_book_fetcher import (
    backfill_option_order_books,
    fetch_option_order_book_for_date,
    get_active_option_codes,
    get_option_codes_active_in_range,
)


class TestGetActiveOptionCodes:
    @patch("src.collectors.option.order_book_fetcher.SessionLocal")
    async def test_returns_active_codes(self, mock_session_local: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = [
            ("code1",),
            ("code2",),
        ]

        codes = await get_active_option_codes()
        assert codes == ["code1", "code2"]

    @patch("src.collectors.option.order_book_fetcher.SessionLocal")
    async def test_empty(self, mock_session_local: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = []

        codes = await get_active_option_codes()
        assert codes == []


class TestGetOptionCodesActiveInRange:
    @patch("src.collectors.option.order_book_fetcher.SessionLocal")
    async def test_filters_by_contract_lifetime_not_last_trade_date(
        self, mock_session_local: MagicMock
    ) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = [("code1",)]

        codes = await get_option_codes_active_in_range(
            date(2026, 7, 30), date(2026, 7, 31)
        )

        assert codes == ["code1"]
        statement = mock_session.execute.call_args.args[0]
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert "option_instruments.expiry_date >= '2026-07-30'" in sql
        assert "option_instruments.listing_date <= '2026-07-31'" in sql
        assert "last_trade_date" not in sql


class TestFetchOptionOrderBookForDate:
    @pytest.fixture
    def mock_client(self) -> MagicMock:
        from src.collectors.option.models import BestLimitEntry

        client = AsyncMock()
        client.get_best_limits.return_value = [
            BestLimitEntry(
                h_even=60123,
                ref_id=15174976313,
                depth_level=1,
                bid_price=18000.0,
                bid_volume=100,
                bid_order_count=5,
                ask_price=20000.0,
                ask_volume=79,
                ask_order_count=1,
            ),
        ]
        return client

    @patch("src.collectors.option.order_book_fetcher.insert_option_order_book")
    async def test_inserts_rows(
        self, mock_insert: MagicMock, mock_client: MagicMock
    ) -> None:
        result = await fetch_option_order_book_for_date(
            client=mock_client,
            instrument_code="3729523725493580",
            trade_date=date(2026, 7, 1),
        )
        assert result == 1
        mock_insert.assert_called_once()
        args = mock_insert.call_args[0][0]
        assert len(args) == 1
        assert args[0]["instrument_code"] == "3729523725493580"

    @patch("src.collectors.option.order_book_fetcher.insert_option_order_book")
    async def test_no_limits_no_insert(
        self, mock_insert: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.get_best_limits.return_value = []
        result = await fetch_option_order_book_for_date(
            client=mock_client,
            instrument_code="code",
            trade_date=date(2026, 7, 1),
        )
        assert result == 0
        mock_insert.assert_not_called()

    @patch("src.collectors.option.order_book_fetcher.insert_option_order_book")
    async def test_insert_failure_is_not_reported_as_saved(
        self, mock_insert: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_insert.side_effect = RuntimeError("ClickHouse insert failed")

        with pytest.raises(RuntimeError, match="ClickHouse insert failed"):
            await fetch_option_order_book_for_date(
                client=mock_client,
                instrument_code="code",
                trade_date=date(2026, 7, 1),
            )


class TestBackfillOptionOrderBooks:
    @patch("src.collectors.option.order_book_fetcher.get_active_option_codes")
    @patch("src.collectors.option.order_book_fetcher.insert_option_order_book")
    async def test_backfill_with_explicit_codes(
        self, mock_insert: MagicMock, mock_get_codes: MagicMock
    ) -> None:
        from src.collectors.option.models import BestLimitEntry

        items_per_request: list[list] = [
            [
                BestLimitEntry(60123, 1, 1, 18000.0, 100, 5, 20000.0, 79, 1),
                BestLimitEntry(60123, 1, 2, 17000.0, 50, 2, 21000.0, 30, 1),
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
            "src.collectors.option.order_book_fetcher.OptionTsetmcClient", mock_client_cls
        ):
            result = await backfill_option_order_books(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 1),
                instrument_codes=["code1", "code2"],
            )

        assert result["total_days_tried"] == 2
        assert result["total_rows"] == 2
        assert result["empty_responses"] == 1
        assert result["errors"] == []
        mock_get_codes.assert_not_called()

    @patch("src.collectors.option.order_book_fetcher.get_active_option_codes")
    async def test_explicit_empty_codes_do_not_fall_back_to_all_active(
        self, mock_get_codes: AsyncMock
    ) -> None:
        result = await backfill_option_order_books(
            start_date=date(2026, 7, 30),
            end_date=date(2026, 7, 31),
            instrument_codes=[],
        )

        assert result == {
            "total_days_tried": 0,
            "total_rows": 0,
            "empty_responses": 0,
            "errors": [],
        }
        mock_get_codes.assert_not_awaited()

    @patch("src.collectors.option.order_book_fetcher.get_active_option_codes")
    @patch("src.collectors.option.order_book_fetcher.insert_option_order_book")
    async def test_backfill_errors(
        self, mock_insert: MagicMock, mock_get_codes: MagicMock
    ) -> None:
        mock_get_codes.return_value = ["code1"]

        mock_client_cls = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.get_best_limits.side_effect = ValueError("boom")
        mock_client_cls.return_value.__aenter__.return_value = mock_client_instance

        with patch(
            "src.collectors.option.order_book_fetcher.OptionTsetmcClient", mock_client_cls
        ):
            result = await backfill_option_order_books(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 1),
            )

        assert result["total_days_tried"] == 0
        assert result["total_rows"] == 0
        assert len(result["errors"]) == 1
        assert "boom" in result["errors"][0]
