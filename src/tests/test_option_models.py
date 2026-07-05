from src.collectors.option.models import MarketWatchItem
from src.collectors.option.transformer import is_option


class TestMarketWatchItemFromRow:
    def test_full_row(self) -> None:
        row = [
            "3729523725493580",
            "IRO9AHRM0A01",
            "ضهرم4023",
            "اختيارخ اهرم-20000-1405/04/31",
            "122858",
            "24000",
        ]
        row += [""] * 19
        row.append("3A")
        item = MarketWatchItem.from_row(row)
        assert item.ins_code == "3729523725493580"
        assert item.instrument_id == "IRO9AHRM0A01"
        assert item.symbol == "ضهرم4023"
        assert item.name == "اختيارخ اهرم-20000-1405/04/31"
        assert item.flow_code == "3A"

    def test_short_row(self) -> None:
        item = MarketWatchItem.from_row(["123", "IRO1", "ضت1", "اختیارخ تپکو-1000-1405/04/31"])
        assert item.ins_code == "123"
        assert item.instrument_id == "IRO1"
        assert item.symbol == "ضت1"
        assert item.flow_code == ""


class TestIsOption:
    def test_call_option_persian_y(self) -> None:
        item = MarketWatchItem(
            ins_code="1",
            instrument_id="IRO1",
            symbol="ضهرم4023",
            name="اختیارخ اهرم-20000-1405/04/31",
            flow_code="3A",
        )
        assert is_option(item) is True

    def test_put_option_arabic_y(self) -> None:
        item = MarketWatchItem(
            ins_code="1",
            instrument_id="IRO1",
            symbol="ضفول4023",
            name="اختيارف فولاد-5000-1405/04/31",
            flow_code="3A",
        )
        assert is_option(item) is True

    def test_not_option(self) -> None:
        item = MarketWatchItem(
            ins_code="1",
            instrument_id="IRO1",
            symbol="اخزا202",
            name="اسنادخزانه-م2بودجه02-050923",
            flow_code="2",
        )
        assert is_option(item) is False

    def test_empty_name(self) -> None:
        item = MarketWatchItem(
            ins_code="1", instrument_id="IRO1", symbol="sym", name="", flow_code=""
        )
        assert is_option(item) is False
