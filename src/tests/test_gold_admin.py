from pathlib import Path

from src.admin.gold.gold_views import GoldInstrumentAdmin
from src.admin.gold.gold_clickhouse_views import GoldOrderBookView, GoldTradesView


def test_gold_admin_views_configuration() -> None:
    assert GoldInstrumentAdmin.category == "Gold Market"
    assert GoldInstrumentAdmin.name == "Gold Instrument"
    assert GoldInstrumentAdmin.name_plural == "Gold Instruments"
    assert GoldInstrumentAdmin.category_icon == "fa-solid fa-coins"

    assert GoldOrderBookView.category == "Gold Market"
    assert GoldOrderBookView.category_icon == "fa-solid fa-coins"
    assert GoldOrderBookView.identity == "gold-order-book"

    assert GoldTradesView.category == "Gold Market"
    assert GoldTradesView.category_icon == "fa-solid fa-coins"
    assert GoldTradesView.identity == "gold-trades"


def test_admin_navigation_registers_gold_views() -> None:
    source = Path("src/admin/__init__.py").read_text()

    for view in ("GoldInstrumentAdmin", "GoldOrderBookView", "GoldTradesView"):
        assert f"admin.add_view({view})" in source
