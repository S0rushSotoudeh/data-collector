from datetime import date
from decimal import Decimal

from src.collectors.stock.models import BestLimitEntry, StockInstrumentInfo, TradeEntry
from src.collectors.stock.transformer import (
    best_limits_to_order_book_rows,
    instrument_info_to_pg_attrs,
    is_stock,
    market_watch_to_pg_attrs,
    trades_to_trade_rows,
)
from src.collectors.stock.models import MarketWatchItem


class TestMarketWatchToPgAttrs:
    def test_basic(self) -> None:
        item = MarketWatchItem(
            ins_code="35100368959864864",
            instrument_id="IRO1FOLD0001",
            symbol="فولاد",
            name="فولاد مباركه اصفهان",
            flow_code="1A",
        )
        attrs = market_watch_to_pg_attrs(item)
        assert attrs["instrument_code"] == "35100368959864864"
        assert attrs["instrument_id"] == "IRO1FOLD0001"
        assert attrs["symbol"] == "فولاد"
        assert attrs["name_fa"] == "فولاد مباركه اصفهان"
        assert attrs["name_en"] == "فولاد مباركه اصفهان"
        assert attrs["status"] == "active"
        assert attrs["is_gold_etf"] is False

    def test_is_stock_consistent(self) -> None:
        item = MarketWatchItem(
            ins_code="1", instrument_id="IRO1", symbol="s", name="اختیارخ x-1-1", flow_code=""
        )
        assert is_stock(item) is False

    def test_gold_etf_classification(self) -> None:
        item = MarketWatchItem(
            ins_code="1", instrument_id="IRO1", symbol="ناشناخته", name="نام موقت", flow_code=""
        )

        assert market_watch_to_pg_attrs(item, is_gold_etf=True)["is_gold_etf"] is True


class TestInstrumentInfoToPgAttrs:
    def _make_info(self) -> StockInstrumentInfo:
        return StockInstrumentInfo(
            ins_code="35100368959864864",
            name_fa="فولاد مباركه اصفهان",
            name_en="Foolad",
            symbol="فولاد",
            isin="IRO1FOLD0001",
            instrument_id="IRO1FOLD0001",
            total_issued=1000000.0,
            base_volume=2,
            flow=1,
            flow_title="بازار اول (اصلي) بورس",
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

    def test_basic(self) -> None:
        info = self._make_info()
        attrs = instrument_info_to_pg_attrs(info, status="active")
        assert attrs["instrument_code"] == "35100368959864864"
        assert attrs["name_fa"] == "فولاد مباركه اصفهان"
        assert attrs["isin"] == "IRO1FOLD0001"
        assert attrs["market_code"] == 1
        assert attrs["market_name"] == "بازار اول (اصلي) بورس"
        assert attrs["security_type_code"] == "59"
        assert attrs["security_type_name"] == "فلزات اساسي"
        assert attrs["price_ceiling"] == Decimal("25500.00")
        assert attrs["low_52w"] == Decimal("24000.00")
        assert attrs["high_yearly"] == Decimal("26000.00")
        assert attrs["avg_daily_volume_5y"] == 500000
        assert attrs["last_trade_date"] == date(2026, 7, 1)
        assert attrs["status"] == "active"
        assert attrs["is_gold_etf"] is False

    def test_gold_etf_from_detailed_name(self) -> None:
        info = self._make_info()

        assert instrument_info_to_pg_attrs(info, is_gold_etf=True)["is_gold_etf"] is True

    def test_no_status(self) -> None:
        info = self._make_info()
        attrs = instrument_info_to_pg_attrs(info)
        assert "status" not in attrs


class TestBestLimitsToOrderBookRows:
    def test_basic_conversion(self) -> None:
        limits = [
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
        rows = best_limits_to_order_book_rows(
            limits=limits,
            instrument_code="35100368959864864",
            trade_date=date(2026, 7, 1),
            data_source="tsetmc",
        )
        assert len(rows) == 1
        r = rows[0]
        assert r["instrument_code"] == "35100368959864864"
        assert r["trade_date"] == date(2026, 7, 1)
        assert r["trade_time"] == 60123
        assert r["depth_level"] == 1
        assert r["bid_price"] == 24000
        assert r["ask_price"] == 24500
        assert r["data_source"] == "tsetmc"

    def test_empty(self) -> None:
        rows = best_limits_to_order_book_rows(
            limits=[], instrument_code="code", trade_date=date(2026, 7, 1)
        )
        assert rows == []


class TestTradesToTradeRows:
    def test_basic(self) -> None:
        trades = [
            TradeEntry(h_even=60123, n_tran=1001, price=24250.0, volume=100, canceled=False),
        ]
        rows = trades_to_trade_rows(trades, "35100368959864864", date(2026, 7, 1), "tsetmc")
        assert len(rows) == 1
        r = rows[0]
        assert r["instrument_code"] == "35100368959864864"
        assert r["trade_id"] == 1001
        assert r["price"] == 24250
        assert r["volume"] == 100
        assert r["value"] == 2425000
        assert r["is_canceled"] == 0

    def test_canceled(self) -> None:
        trades = [TradeEntry(h_even=60124, n_tran=1002, price=24300.0, volume=10, canceled=True)]
        rows = trades_to_trade_rows(trades, "code", date(2026, 7, 1), "tsetmc")
        assert rows[0]["is_canceled"] == 1
