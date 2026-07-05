from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.option.instrument_sync import sync_option_instruments_to_pg
from src.collectors.option.models import MarketWatchItem, OptionInstrumentInfo


def _make_item(code: str, name: str) -> MarketWatchItem:
    return MarketWatchItem(
        ins_code=code,
        instrument_id=f"IRO{code}",
        symbol=f"ض{code}",
        name=name,
        flow_code="3A",
    )


class TestSyncOptionInstrumentsToPg:
    @pytest.fixture
    def mock_client(self) -> MagicMock:
        m = AsyncMock()
        m.get_market_watch.return_value = [
            _make_item("3729523725493580", "اختیارخ اهرم-20000-1405/04/31"),
            _make_item("999", "اختیارف فولاد-5000-1405/04/31"),
            _make_item("888", "اسنادخزانه-م2بودجه02"),
        ]
        m.get_instrument_info.return_value = OptionInstrumentInfo(
            ins_code="3729523725493580",
            name_fa="اختیارخ اهرم-20000-1405/04/31",
            name_en="اختیارخ اهرم-20000-1405/04/31",
            symbol="ضهرم4023",
            isin="IRO9AHRM0A01",
            instrument_id="IRO9AHRM0A01",
            total_issued=1000000.0,
            base_volume=1,
            flow=4,
            flow_title="بازار پایه",
            cgr_val_cot="I1",
            cgr_val_cot_title="ابزارهاي نوين",
            c_sec_val="69",
            l_sec_val="اوراق تامين مالي",
            price_ceiling=25000.0,
            price_floor=15000.0,
            min_week=18000.0,
            max_week=22000.0,
            min_year=10000.0,
            max_year=25000.0,
            avg_daily_volume_5y=500.0,
            d_even=20260701,
        )
        return m

    @patch("src.collectors.option.instrument_sync.SessionLocal")
    async def test_sync_success_filters_non_options(
        self, mock_session_local: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        result = await sync_option_instruments_to_pg(mock_client)

        assert result["synced"] == 2
        assert result["errors"] == []
        assert mock_session.merge.call_count == 2
        assert mock_session.commit.call_count == 2

    @patch("src.collectors.option.instrument_sync.SessionLocal")
    async def test_sync_with_error(
        self, mock_session_local: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.get_instrument_info = AsyncMock(side_effect=ValueError("API error"))
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        result = await sync_option_instruments_to_pg(mock_client)

        assert result["synced"] == 0
        assert len(result["errors"]) == 2

    @patch("src.collectors.option.instrument_sync.SessionLocal")
    async def test_sync_empty_market_watch(
        self, mock_session_local: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.get_market_watch.return_value = []

        result = await sync_option_instruments_to_pg(mock_client)

        assert result["synced"] == 0
        assert result["errors"] == []
