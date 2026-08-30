from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.stock.instrument_sync import sync_stock_instruments_to_pg
from src.collectors.stock.models import MarketWatchItem, StockInstrumentInfo


def _make_item(code: str, name: str) -> MarketWatchItem:
    return MarketWatchItem(
        ins_code=code,
        instrument_id=f"IRO{code}",
        symbol=f"س{code}",
        name=name,
        flow_code="1A",
    )


class TestSyncStockInstrumentsToPg:
    @pytest.fixture
    def mock_client(self) -> MagicMock:
        m = AsyncMock()
        m.get_market_watch.return_value = [
            _make_item("35100368959864864", "فولاد مباركه اصفهان"),
            _make_item("35100368959864865", "سپنتا"),
            _make_item("999", "اختیارخ اهرم-20000-1405/04/31"),
            _make_item("888", "اسنادخزانه-م2بودجه02"),
        ]
        m.get_instrument_info.return_value = StockInstrumentInfo(
            ins_code="35100368959864864",
            name_fa="فولاد مبارکہ اصفهان",
            name_en="Foolad",
            symbol="فولاد",
            isin="IRO1FOLD0001",
            instrument_id="IRO1FOLD0001",
            total_issued=1000000.0,
            base_volume=2,
            flow=1,
            flow_title="بازار اول",
            cgr_val_cot="91",
            cgr_val_cot_title="بازار اول",
            c_sec_val="59",
            l_sec_val="فلزات اساسي",
            price_ceiling=25500.0,
            price_floor=23500.0,
            min_week=24000.0,
            max_week=25000.0,
            min_year=20000.0,
            max_year=26000.0,
            avg_daily_volume_5y=500000.0,
            d_even=20260701,
        )
        return m

    @pytest.fixture
    def mock_ime_client(self) -> MagicMock:
        client = AsyncMock()
        client.get_gold_etf_ins_codes.return_value = set()
        return client

    @patch("src.collectors.stock.instrument_sync.SessionLocal")
    async def test_sync_success_filters_non_stocks(
        self, mock_session_local: MagicMock, mock_client: MagicMock, mock_ime_client: MagicMock
    ) -> None:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        result = await sync_stock_instruments_to_pg(mock_client, ime_client=mock_ime_client)

        assert result["synced"] == 2
        assert result["errors"] == []
        assert mock_session.merge.call_count == 2
        assert mock_session.commit.call_count == 2
        mock_ime_client.get_gold_etf_ins_codes.assert_awaited_once()

    @patch("src.collectors.stock.instrument_sync.SessionLocal")
    async def test_sync_with_error(
        self, mock_session_local: MagicMock, mock_client: MagicMock, mock_ime_client: MagicMock
    ) -> None:
        mock_client.get_instrument_info = AsyncMock(side_effect=ValueError("API error"))
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        result = await sync_stock_instruments_to_pg(mock_client, ime_client=mock_ime_client)

        assert result["synced"] == 0
        assert len(result["errors"]) == 2

    @patch("src.collectors.stock.instrument_sync.SessionLocal")
    async def test_sync_empty_market_watch(
        self, mock_session_local: MagicMock, mock_client: MagicMock, mock_ime_client: MagicMock
    ) -> None:
        mock_client.get_market_watch.return_value = []

        result = await sync_stock_instruments_to_pg(mock_client, ime_client=mock_ime_client)

        assert result["synced"] == 0
        assert result["errors"] == []

    @patch("src.collectors.stock.instrument_sync.SessionLocal")
    async def test_sync_uses_official_ime_codes_for_gold_flag(
        self, mock_session_local: MagicMock, mock_client: MagicMock, mock_ime_client: MagicMock
    ) -> None:
        mock_client.get_market_watch.return_value = [
            MarketWatchItem(
                ins_code="35100368959864864",
                instrument_id="IRO1GOLD0001",
                symbol="ETF123",
                name="نام موقت",
                flow_code="1A",
            )
        ]
        mock_ime_client.get_gold_etf_ins_codes.return_value = {"35100368959864864"}
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        result = await sync_stock_instruments_to_pg(mock_client, ime_client=mock_ime_client)

        assert result["synced"] == 1
        instrument = mock_session.merge.call_args.args[0]
        assert instrument.is_gold_etf is True

    @patch("src.collectors.stock.instrument_sync.SessionLocal")
    async def test_sync_stops_before_writes_when_official_list_fails(
        self, mock_session_local: MagicMock, mock_client: MagicMock, mock_ime_client: MagicMock
    ) -> None:
        mock_ime_client.get_gold_etf_ins_codes.side_effect = RuntimeError("IME unavailable")

        with pytest.raises(RuntimeError, match="IME unavailable"):
            await sync_stock_instruments_to_pg(mock_client, ime_client=mock_ime_client)

        mock_client.get_market_watch.assert_not_awaited()
        mock_session_local.assert_not_called()
