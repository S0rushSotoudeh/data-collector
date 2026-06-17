from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.bond.instrument_sync import sync_instruments_to_pg
from src.collectors.bond.models import BondInstrumentInfo, BondSearchItem


class TestSyncInstrumentsToPg:
    @pytest.fixture
    def mock_client(self) -> MagicMock:
        m = AsyncMock()
        m.search_instruments.return_value = [
            BondSearchItem(
                ins_code="36408112396351116",
                name_fa="اخزا202",
                symbol="اخزا202",
                flow=2,
                flow_title="بازار فرابورس",
                cgr_val_cot="I1",
                cgr_val_cot_title="بازار ابزارهاي نوين مالي فرابورس",
                last_date=1,
            ),
            BondSearchItem(
                ins_code="3577388800305243",
                name_fa="اخزا001",
                symbol="اخزا001",
                flow=2,
                flow_title="بازار فرابورس",
                cgr_val_cot="I1",
                cgr_val_cot_title="بازار ابزارهاي نوين مالي فرابورس",
                last_date=0,
            ),
        ]
        m.get_instrument_info.return_value = BondInstrumentInfo(
            ins_code="36408112396351116",
            name_fa="اخزا202",
            name_en="TreasuryBill261214",
            symbol="اخزا202",
            isin="IRB3TR160593",
            instrument_id="IRB3TR160591",
            total_issued=150000000.0,
            base_volume=1,
            flow=2,
            flow_title="بازار فرابورس",
            cgr_val_cot="I1",
            cgr_val_cot_title="بازار ابزارهاي نوين مالي فرابورس",
            c_sec_val="69",
            l_sec_val="اوراق تامين مالي",
            price_ceiling=867440.0,
            price_floor=816920.0,
            min_week=838150.0,
            max_week=844910.0,
            min_year=615670.0,
            max_year=844910.0,
            avg_daily_volume_5y=29068.0,
            d_even=20260610,
        )
        return m

    @patch("src.collectors.bond.instrument_sync.SessionLocal")
    async def test_sync_success(
        self, mock_session_local: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        result = await sync_instruments_to_pg(mock_client)

        assert result["synced"] == 2
        assert result["errors"] == []
        assert mock_session.merge.call_count == 2
        assert mock_session.commit.call_count == 2

    @patch("src.collectors.bond.instrument_sync.SessionLocal")
    async def test_sync_with_error(
        self, mock_session_local: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.get_instrument_info = AsyncMock(
            side_effect=ValueError("API error")
        )
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        result = await sync_instruments_to_pg(mock_client)

        assert result["synced"] == 0
        assert len(result["errors"]) == 2

    @patch("src.collectors.bond.instrument_sync.SessionLocal")
    async def test_sync_empty_search(
        self, mock_session_local: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.search_instruments.return_value = []

        result = await sync_instruments_to_pg(mock_client)

        assert result["synced"] == 0
        assert result["errors"] == []