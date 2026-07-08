from src.collectors.stock.models import MarketWatchItem
from src.collectors.stock.transformer import is_bond, is_option, is_stock


class TestMarketWatchItemFromRow:
    def test_full_row(self) -> None:
        row = [
            "35100368959864864",
            "IRO1FOLD0001",
            "فولاد",
            "فولاد مباركه اصفهان",
            "122858",
            "24000",
        ]
        row += [""] * 19
        row.append("1A")
        item = MarketWatchItem.from_row(row)
        assert item.ins_code == "35100368959864864"
        assert item.instrument_id == "IRO1FOLD0001"
        assert item.symbol == "فولاد"
        assert item.name == "فولاد مباركه اصفهان"
        assert item.flow_code == "1A"

    def test_short_row(self) -> None:
        item = MarketWatchItem.from_row(["123", "IRO1", "پارس", "سپنتا"])
        assert item.ins_code == "123"
        assert item.instrument_id == "IRO1"
        assert item.symbol == "پارس"
        assert item.flow_code == ""


class TestIsStock:
    def test_stock(self) -> None:
        item = MarketWatchItem(
            ins_code="1",
            instrument_id="IRO1FOLD0001",
            symbol="فولاد",
            name="فولاد مباركه اصفهان",
            flow_code="1A",
        )
        assert is_stock(item) is True

    def test_option_excluded(self) -> None:
        item = MarketWatchItem(
            ins_code="1",
            instrument_id="IRO1",
            symbol="ضهرم4023",
            name="اختیارخ اهرم-20000-1405/04/31",
            flow_code="3A",
        )
        assert is_stock(item) is False

    def test_option_arabic_y_excluded(self) -> None:
        item = MarketWatchItem(
            ins_code="1",
            instrument_id="IRO1",
            symbol="ضفول4023",
            name="اختيارف فولاد-5000-1405/04/31",
            flow_code="3A",
        )
        assert is_stock(item) is False

    def test_bond_excluded(self) -> None:
        item = MarketWatchItem(
            ins_code="1",
            instrument_id="IRO1",
            symbol="اخزا202",
            name="اسنادخزانه-م2بودجه02-050923",
            flow_code="2",
        )
        assert is_stock(item) is False

    def test_is_option_helper(self) -> None:
        item = MarketWatchItem(
            ins_code="1", instrument_id="IRO1", symbol="s", name="اختیارخ x-1-1405/01/01", flow_code=""
        )
        assert is_option(item) is True

    def test_is_bond_helper(self) -> None:
        item = MarketWatchItem(
            ins_code="1", instrument_id="IRO1", symbol="s", name="اسنادخزانه-م2بودجه02", flow_code=""
        )
        assert is_bond(item) is True

    def test_empty_name(self) -> None:
        item = MarketWatchItem(
            ins_code="1", instrument_id="IRO1", symbol="sym", name="", flow_code=""
        )
        assert is_stock(item) is True
