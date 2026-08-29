from datetime import date
from decimal import Decimal

from src.collectors.gold.models import (
    BestLimitEntry,
    GoldInstrumentInfo,
    MarketWatchItem,
    TradeEntry,
)
from src.collectors.gold.transformer import (
    best_limits_to_order_book_rows,
    instrument_info_to_pg_attrs,
    is_gold,
    market_watch_to_pg_attrs,
    trades_to_trade_rows,
)


def test_is_gold():
    gold_etf = MarketWatchItem(
        ins_code="123", instrument_id="GLD1", symbol="عیار", name="صندوق طلا عیار", flow_code="1"
    )
    gold_cert = MarketWatchItem(
        ins_code="124", instrument_id="GLD2", symbol="سکه0312پ01", name="گواهی سپرده سکه طلا", flow_code="1"
    )
    stock = MarketWatchItem(
        ins_code="125", instrument_id="STK1", symbol="فولاد", name="فولاد مبارکه اصفهان", flow_code="1"
    )

    assert is_gold(gold_etf) is True
    assert is_gold(gold_cert) is False
    assert is_gold(stock) is False


def test_trades_to_trade_rows():
    trades = [
        TradeEntry(h_even=123000, n_tran=1, price=100_000.0, volume=50, canceled=False)
    ]
    rows = trades_to_trade_rows(trades, "123", date(2026, 8, 29))
    assert len(rows) == 1
    assert rows[0]["instrument_code"] == "123"
    assert rows[0]["price"] == 100_000
    assert rows[0]["volume"] == 50
    assert rows[0]["value"] == 100_000 * 50


def test_best_limits_to_order_book_rows():
    limits = [
        BestLimitEntry(
            h_even=123000,
            ref_id=10,
            depth_level=1,
            bid_price=99_000.0,
            bid_volume=10,
            bid_order_count=2,
            ask_price=101_000.0,
            ask_volume=20,
            ask_order_count=3,
        )
    ]
    rows = best_limits_to_order_book_rows(limits, "123", date(2026, 8, 29))
    assert len(rows) == 1
    assert rows[0]["depth_level"] == 1
    assert rows[0]["bid_price"] == 99_000
    assert rows[0]["ask_price"] == 101_000


def test_instrument_info_to_pg_attrs():
    info = GoldInstrumentInfo(
        ins_code="123",
        name_fa="صندوق طلا عیار",
        name_en="Ayat Gold Fund",
        symbol="عیار",
        isin="IRO1GLD00001",
        instrument_id="GLD001",
        total_issued=1000.0,
        base_volume=1,
        flow=1,
        flow_title="بورس",
        cgr_val_cot="1",
        cgr_val_cot_title="عادی",
        c_sec_val="1",
        l_sec_val="سهام",
        price_ceiling=110_000.0,
        price_floor=90_000.0,
        min_week=95_000.0,
        max_week=105_000.0,
        min_year=80_000.0,
        max_year=120_000.0,
        avg_daily_volume_5y=500.0,
        d_even=20260829,
    )
    attrs = instrument_info_to_pg_attrs(info, status="active")
    assert attrs["instrument_code"] == "123"
    assert attrs["symbol"] == "عیار"
    assert attrs["price_ceiling"] == Decimal("110000.0")
    assert attrs["last_trade_date"] == date(2026, 8, 29)
    assert attrs["status"] == "active"


def test_parse_ime_funds_html():
    from src.collectors.gold.transformer import parse_ime_funds_html
    sample_html = """
    <table>
      <tr><td>طلا</td><td>عیار</td><td><a href="http://tsetmc.com/Loader.aspx?ParTree=151311&i=35100368959864864">Link</a></td></tr>
      <tr><td>شاخه طلا</td><td>گوهر</td><td><a href="instInfo/456">Link</a></td></tr>
      <tr><td>سهام</td><td>فولاد</td><td><a href="instInfo/789">Link</a></td></tr>
    </table>
    """
    funds = parse_ime_funds_html(sample_html)
    assert len(funds) == 2
    assert funds[0] == {"symbol": "عیار", "ins_code": "35100368959864864"}
    assert funds[1] == {"symbol": "گوهر", "ins_code": "456"}
