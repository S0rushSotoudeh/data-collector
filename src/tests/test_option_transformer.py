from datetime import date
from decimal import Decimal

from src.collectors.option.models import BestLimitEntry, OptionInstrumentInfo, TradeEntry
from src.collectors.option.transformer import (
    best_limits_to_order_book_rows,
    instrument_info_to_pg_attrs,
    market_watch_to_pg_attrs,
    parse_option_name,
    trades_to_trade_rows,
)


class TestParseOptionName:
    def test_call_with_persian_y(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name(
            "اختیارخ اهرم-20000-1405/04/31"
        )
        assert opt_type == "call"
        assert underlying == "اهرم"
        assert strike == Decimal("20000")
        assert expiry == date(2026, 7, 22)

    def test_put_with_arabic_y(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name(
            "اختيارف فولاد-5000-1405/12/29"
        )
        assert opt_type == "put"
        assert underlying == "فولاد"
        assert strike == Decimal("5000")
        assert expiry == date(2027, 3, 20)

    def test_no_match(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name("اسنادخزانه")
        assert opt_type is None
        assert underlying is None
        assert strike is None
        assert expiry is None

    def test_expiry_8digit_no_separators(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name(
            "اختیارخ موج-42000-14050629"
        )
        assert opt_type == "call"
        assert underlying == "موج"
        assert strike == Decimal("42000")
        assert expiry == date(2026, 9, 20)

    def test_expiry_2digit_year_slashes(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name(
            "اختیارف جوانه.ک-20000-05/04/24"
        )
        assert opt_type == "put"
        assert underlying == "جوانه.ک"
        assert strike == Decimal("20000")
        assert expiry == date(2026, 7, 15)

    def test_expiry_full_slashes(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name(
            "اختیارخ وبصادر-380-1405/07/22"
        )
        assert opt_type == "call"
        assert underlying == "وبصادر"
        assert strike == Decimal("380")
        assert expiry == date(2026, 10, 14)

    def test_expiry_dash_separators(self) -> None:
        opt_type, _, strike, expiry = parse_option_name(
            "اختیارخ اهرم-20000-1405-04-31"
        )
        assert opt_type == "call"
        assert strike == Decimal("20000")
        assert expiry == date(2026, 7, 22)

    def test_none(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name(None)
        assert opt_type is None
        assert expiry is None

    def test_underlying_with_space_put(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name(
            "اختيارف هم تراز-12000-05/08/06"
        )
        assert opt_type == "put"
        assert underlying == "هم تراز"
        assert strike == Decimal("12000")
        assert expiry == date(2026, 10, 28)

    def test_underlying_with_space_call(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name(
            "اختیارخ هم تراز-11000-05/06/04"
        )
        assert opt_type == "call"
        assert underlying == "هم تراز"
        assert strike == Decimal("11000")
        assert expiry == date(2026, 8, 26)

    def test_english_format_no_match(self) -> None:
        opt_type, underlying, strike, expiry = parse_option_name("TRZZ-O-14050806")
        assert opt_type is None
        assert underlying is None
        assert strike is None
        assert expiry is None


class TestMarketWatchToPgAttrs:
    def test_basic(self) -> None:
        from src.collectors.option.models import MarketWatchItem

        item = MarketWatchItem(
            ins_code="3729523725493580",
            instrument_id="IRO9AHRM0A01",
            symbol="ضهرم4023",
            name="اختیارخ اهرم-20000-1405/04/31",
            flow_code="3A",
        )
        attrs = market_watch_to_pg_attrs(item)
        assert attrs["instrument_code"] == "3729523725493580"
        assert attrs["instrument_id"] == "IRO9AHRM0A01"
        assert attrs["symbol"] == "ضهرم4023"
        assert attrs["name_en"] == "اختیارخ اهرم-20000-1405/04/31"
        assert attrs["option_type"] == "call"
        assert attrs["underlying_symbol"] == "اهرم"
        assert attrs["strike_price"] == Decimal("20000")
        assert attrs["expiry_date"] == date(2026, 7, 22)
        assert attrs["status"] == "active"


class TestInstrumentInfoToPgAttrs:
    def _make_info(self, name_fa: str | None = None, name_en: str | None = None) -> OptionInstrumentInfo:
        return OptionInstrumentInfo(
            ins_code="3729523725493580",
            name_fa=name_fa,
            name_en=name_en,
            symbol="ضهرم4023",
            isin="IRO9AHRM0A01",
            instrument_id="IRO9AHRM0A01",
            total_issued=1000000.0,
            base_volume=1,
            flow=4,
            flow_title="بازار پایه فرابورس",
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

    def test_option_fields_from_name_fa(self) -> None:
        info = self._make_info(name_fa="اختیارخ اهرم-20000-1405/04/31")
        attrs = instrument_info_to_pg_attrs(info, status="active")
        assert attrs["instrument_code"] == "3729523725493580"
        assert attrs["option_type"] == "call"
        assert attrs["underlying_symbol"] == "اهرم"
        assert attrs["strike_price"] == Decimal("20000")
        assert attrs["expiry_date"] == date(2026, 7, 22)
        assert attrs["status"] == "active"
        assert attrs["last_trade_date"] == date(2026, 7, 1)
        assert attrs["price_ceiling"] == Decimal("25000.00")
        assert attrs["market_code"] == 4

    def test_falls_back_to_name_en(self) -> None:
        info = self._make_info(name_fa="ضهرم4023", name_en="اختیارف فولاد-5000-1405/12/29")
        attrs = instrument_info_to_pg_attrs(info)
        assert attrs["option_type"] == "put"
        assert attrs["underlying_symbol"] == "فولاد"
        assert attrs["strike_price"] == Decimal("5000")

    def test_no_status(self) -> None:
        info = self._make_info(name_fa="اختیارخ اهرم-20000-1405/04/31")
        attrs = instrument_info_to_pg_attrs(info)
        assert "status" not in attrs


class TestBestLimitsToOrderBookRows:
    def test_basic_conversion(self) -> None:
        limits = [
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
        rows = best_limits_to_order_book_rows(
            limits=limits,
            instrument_code="3729523725493580",
            trade_date=date(2026, 7, 1),
            data_source="tsetmc",
        )
        assert len(rows) == 1
        r = rows[0]
        assert r["instrument_code"] == "3729523725493580"
        assert r["trade_date"] == date(2026, 7, 1)
        assert r["trade_time"] == 60123
        assert r["depth_level"] == 1
        assert r["bid_price"] == 18000
        assert r["ask_price"] == 20000
        assert r["data_source"] == "tsetmc"

    def test_empty(self) -> None:
        rows = best_limits_to_order_book_rows(
            limits=[], instrument_code="code", trade_date=date(2026, 7, 1)
        )
        assert rows == []


class TestTradesToTradeRows:
    def test_basic(self) -> None:
        trades = [
            TradeEntry(h_even=60123, n_tran=1001, price=20000.0, volume=50, canceled=False),
        ]
        rows = trades_to_trade_rows(trades, "3729523725493580", date(2026, 7, 1), "tsetmc")
        assert len(rows) == 1
        r = rows[0]
        assert r["instrument_code"] == "3729523725493580"
        assert r["trade_id"] == 1001
        assert r["price"] == 20000
        assert r["volume"] == 50
        assert r["value"] == 1000000
        assert r["is_canceled"] == 0
