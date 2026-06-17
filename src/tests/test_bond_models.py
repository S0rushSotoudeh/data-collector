from datetime import date

from src.collectors.bond.models import BestLimitEntry, BondInstrumentInfo, BondSearchItem


class TestBondSearchItem:
    def test_from_dict_full(self) -> None:
        raw = {
            "insCode": "36408112396351116",
            "lVal30": "اسنادخزانه-م2بودجه02-050923",
            "lVal18AFC": "اخزا202",
            "flow": 2,
            "flowTitle": "بازار فرابورس",
            "cgrValCot": "I1",
            "cgrValCotTitle": "بازار ابزارهاي نوين مالي فرابورس",
            "lastDate": 1,
        }
        item = BondSearchItem.from_dict(raw)
        assert item.ins_code == "36408112396351116"
        assert item.name_fa == "اسنادخزانه-م2بودجه02-050923"
        assert item.symbol == "اخزا202"
        assert item.flow == 2
        assert item.flow_title == "بازار فرابورس"
        assert item.cgr_val_cot == "I1"
        assert item.last_date == 1

    def test_from_dict_minimal(self) -> None:
        item = BondSearchItem.from_dict({"insCode": "123"})
        assert item.ins_code == "123"
        assert item.name_fa is None
        assert item.symbol is None
        assert item.last_date is None

    def test_from_dict_empty(self) -> None:
        item = BondSearchItem.from_dict({})
        assert item.ins_code == ""
        assert item.name_fa is None


class TestBondInstrumentInfo:
    def test_from_dict_full(self) -> None:
        raw = {
            "insCode": "36408112396351116",
            "lVal30": "اسنادخزانه-م2بودجه02-050923",
            "lVal18": "TreasuryBill261214",
            "lVal18AFC": "اخزا202",
            "cIsin": "IRB3TR160593",
            "instrumentID": "IRB3TR160591",
            "zTitad": 150000000.0,
            "baseVol": 1,
            "flow": 2,
            "flowTitle": "بازار فرابورس",
            "cgrValCot": "I1",
            "cgrValCotTitle": "بازار ابزارهاي نوين مالي فرابورس",
            "cSecVal": "69",
            "lSecVal": "اوراق تامين مالي",
            "staticThreshold": {
                "psGelStaMax": 867440.00,
                "psGelStaMin": 816920.00,
            },
            "minWeek": 838150.00,
            "maxWeek": 844910.00,
            "minYear": 615670.00,
            "maxYear": 844910.00,
            "qTotTran5JAvg": 29068.0,
            "dEven": 20260610,
        }
        info = BondInstrumentInfo.from_dict(raw)
        assert info.ins_code == "36408112396351116"
        assert info.name_fa == "اسنادخزانه-م2بودجه02-050923"
        assert info.name_en == "TreasuryBill261214"
        assert info.symbol == "اخزا202"
        assert info.isin == "IRB3TR160593"
        assert info.instrument_id == "IRB3TR160591"
        assert info.total_issued == 150000000.0
        assert info.base_volume == 1
        assert info.flow == 2
        assert info.flow_title == "بازار فرابورس"
        assert info.cgr_val_cot == "I1"
        assert info.price_ceiling == 867440.00
        assert info.price_floor == 816920.00
        assert info.min_week == 838150.00
        assert info.max_week == 844910.00
        assert info.min_year == 615670.00
        assert info.max_year == 844910.00
        assert info.avg_daily_volume_5y == 29068.0
        assert info.d_even == 20260610

    def test_from_dict_no_static_threshold(self) -> None:
        raw = {"insCode": "123"}
        info = BondInstrumentInfo.from_dict(raw)
        assert info.ins_code == "123"
        assert info.price_ceiling is None
        assert info.price_floor is None


class TestBestLimitEntry:
    def test_from_dict_full(self) -> None:
        raw = {
            "hEven": 60123,
            "refID": 15174976313,
            "number": 1,
            "pMeDem": 821000.0,
            "qTitMeDem": 100,
            "zOrdMeDem": 5,
            "pMeOf": 821980.0,
            "qTitMeOf": 79,
            "zOrdMeOf": 1,
        }
        entry = BestLimitEntry.from_dict(raw)
        assert entry.h_even == 60123
        assert entry.ref_id == 15174976313
        assert entry.depth_level == 1
        assert entry.bid_price == 821000.0
        assert entry.bid_volume == 100
        assert entry.bid_order_count == 5
        assert entry.ask_price == 821980.0
        assert entry.ask_volume == 79
        assert entry.ask_order_count == 1

    def test_from_dict_minimal(self) -> None:
        entry = BestLimitEntry.from_dict({})
        assert entry.h_even == 0
        assert entry.ref_id == 0
        assert entry.depth_level == 0
        assert entry.bid_price == 0.0
        assert entry.bid_volume == 0
        assert entry.bid_order_count == 0
        assert entry.ask_price == 0.0
        assert entry.ask_volume == 0
        assert entry.ask_order_count == 0