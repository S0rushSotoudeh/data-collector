from datetime import date
from decimal import Decimal

from src.collectors.bond.models import BestLimitEntry, BondInstrumentInfo
from src.collectors.bond.transformer import (
    best_limits_to_order_book_rows,
    instrument_info_to_pg_attrs,
    search_item_to_pg_attrs,
)


class TestBestLimitsToOrderBookRows:
    def test_basic_conversion(self) -> None:
        limits = [
            BestLimitEntry(
                h_even=60123,
                ref_id=15174976313,
                depth_level=1,
                bid_price=0.0,
                bid_volume=0,
                bid_order_count=0,
                ask_price=821980.0,
                ask_volume=79,
                ask_order_count=1,
            ),
            BestLimitEntry(
                h_even=60123,
                ref_id=15174976313,
                depth_level=2,
                bid_price=810000.0,
                bid_volume=50,
                bid_order_count=2,
                ask_price=822000.0,
                ask_volume=30,
                ask_order_count=1,
            ),
        ]
        rows = best_limits_to_order_book_rows(
            limits=limits,
            instrument_code="36408112396351116",
            trade_date=date(2026, 6, 10),
            data_source="tsetmc",
        )
        assert len(rows) == 2

        r1 = rows[0]
        assert r1["instrument_code"] == "36408112396351116"
        assert r1["trade_date"] == date(2026, 6, 10)
        assert r1["trade_time"] == 60123
        assert r1["depth_level"] == 1
        assert r1["bid_price"] == 0
        assert r1["ask_price"] == 821980
        assert r1["data_source"] == "tsetmc"
        assert "ingested_at" in r1

        r2 = rows[1]
        assert r2["depth_level"] == 2
        assert r2["bid_price"] == 810000
        assert r2["ask_price"] == 822000

    def test_empty_input(self) -> None:
        rows = best_limits_to_order_book_rows(
            limits=[],
            instrument_code="code",
            trade_date=date(2026, 6, 10),
        )
        assert rows == []


class TestInstrumentInfoToPgAttrs:
    def test_basic_conversion(self) -> None:
        info = BondInstrumentInfo(
            ins_code="36408112396351116",
            name_fa="اسنادخزانه-م2بودجه02-050923",
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
            price_ceiling=867440.00,
            price_floor=816920.00,
            min_week=838150.00,
            max_week=844910.00,
            min_year=615670.00,
            max_year=844910.00,
            avg_daily_volume_5y=29068.0,
            d_even=20260610,
        )
        attrs = instrument_info_to_pg_attrs(info, status="active")
        assert attrs["instrument_code"] == "36408112396351116"
        assert attrs["name_fa"] == "اسنادخزانه-م2بودجه02-050923"
        assert attrs["name_en"] == "TreasuryBill261214"
        assert attrs["symbol"] == "اخزا202"
        assert attrs["isin"] == "IRB3TR160593"
        assert attrs["instrument_id"] == "IRB3TR160591"
        assert attrs["total_issued"] == 150000000
        assert attrs["base_volume"] == 1
        assert attrs["market_code"] == 2
        assert attrs["market_name"] == "بازار فرابورس"
        assert attrs["segment_code"] == "I1"
        assert attrs["segment_name"] == "بازار ابزارهاي نوين مالي فرابورس"
        assert attrs["security_type_code"] == "69"
        assert attrs["security_type_name"] == "اوراق تامين مالي"
        assert attrs["price_ceiling"] == Decimal("867440.00")
        assert attrs["price_floor"] == Decimal("816920.00")
        assert attrs["low_52w"] == Decimal("838150.00")
        assert attrs["high_52w"] == Decimal("844910.00")
        assert attrs["low_yearly"] == Decimal("615670.00")
        assert attrs["high_yearly"] == Decimal("844910.00")
        assert attrs["avg_daily_volume_5y"] == 29068
        assert attrs["last_trade_date"] == date(2026, 6, 10)
        assert attrs["maturity_date"] == date(2026, 12, 14)
        assert attrs["status"] == "active"

    def test_no_status(self) -> None:
        info = BondInstrumentInfo(
            ins_code="123",
            name_fa=None,
            name_en=None,
            symbol=None,
            isin=None,
            instrument_id=None,
            total_issued=None,
            base_volume=None,
            flow=None,
            flow_title=None,
            cgr_val_cot=None,
            cgr_val_cot_title=None,
            c_sec_val=None,
            l_sec_val=None,
            price_ceiling=None,
            price_floor=None,
            min_week=None,
            max_week=None,
            min_year=None,
            max_year=None,
            avg_daily_volume_5y=None,
            d_even=None,
        )
        attrs = instrument_info_to_pg_attrs(info)
        assert "status" not in attrs

    def test_d_even_zero(self) -> None:
        info = BondInstrumentInfo(
            ins_code="123",
            name_fa=None, name_en=None, symbol=None,
            isin=None, instrument_id=None, total_issued=None,
            base_volume=None, flow=None, flow_title=None,
            cgr_val_cot=None, cgr_val_cot_title=None,
            c_sec_val=None, l_sec_val=None,
            price_ceiling=None, price_floor=None,
            min_week=None, max_week=None, min_year=None, max_year=None,
            avg_daily_volume_5y=None, d_even=0,
        )
        attrs = instrument_info_to_pg_attrs(info)
        assert attrs["last_trade_date"] is None


class TestSearchItemToPgAttrs:
    def test_active(self) -> None:
        attrs = search_item_to_pg_attrs(
            ins_code="36408112396351116",
            name_fa="اسنادخزانه-م2بودجه02-050923",
            symbol="اخزا202",
            flow=2,
            flow_title="بازار فرابورس",
            cgr_val_cot="I1",
            cgr_val_cot_title="بازار ابزارهاي نوين مالي فرابورس",
            last_date=1,
        )
        assert attrs["instrument_code"] == "36408112396351116"
        assert attrs["status"] == "active"

    def test_expired(self) -> None:
        attrs = search_item_to_pg_attrs(
            ins_code="123",
            name_fa=None,
            symbol=None,
            flow=None,
            flow_title=None,
            cgr_val_cot=None,
            cgr_val_cot_title=None,
            last_date=0,
        )
        assert attrs["status"] == "expired"