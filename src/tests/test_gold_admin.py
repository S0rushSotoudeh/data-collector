from unittest.mock import AsyncMock, patch

from starlette.datastructures import Headers
from starlette.requests import Request

from src.admin._render import _TEMPLATE_ENV
from src.admin.gold.views import (
    GoldInstrumentAdmin,
    GoldOrderBookView,
    GoldTradesView,
)


def test_gold_templates_compile() -> None:
    _TEMPLATE_ENV.get_template("gold/gold_order_book_list.html")
    _TEMPLATE_ENV.get_template("gold/gold_trades_list.html")


def test_gold_views_category_and_identity() -> None:
    assert GoldInstrumentAdmin.category == "Gold Market"
    assert GoldInstrumentAdmin.identity == "gold-instrument"
    assert GoldOrderBookView.category == "Gold Market"
    assert GoldOrderBookView.identity == "gold-order-book"
    assert GoldTradesView.category == "Gold Market"
    assert GoldTradesView.identity == "gold-trades"


@patch("src.admin.gold.views.count_stock_order_book", new_callable=AsyncMock)
@patch("src.admin.gold.views.get_stock_order_book_paginated", new_callable=AsyncMock)
async def test_gold_order_book_fetch(mock_get, mock_count) -> None:
    mock_count.return_value = 10
    mock_get.return_value = [{"instrument_code": "gold1"}]

    view = GoldOrderBookView()
    total, rows = await view.fetch(
        {"instrument_code": "gold1", "trade_date": "2026-08-01", "depth_level": 1, "data_source": "tsetmc"},
        offset=0,
        limit=50,
    )
    assert total == 10
    assert rows == [{"instrument_code": "gold1"}]
    mock_count.assert_awaited_once()
    mock_get.assert_awaited_once()


@patch("src.admin.gold.views.count_stock_trades", new_callable=AsyncMock)
@patch("src.admin.gold.views.get_stock_trades_paginated", new_callable=AsyncMock)
async def test_gold_trades_fetch(mock_get, mock_count) -> None:
    mock_count.return_value = 5
    mock_get.return_value = [{"instrument_code": "gold1", "price": 1000}]

    view = GoldTradesView()
    total, rows = await view.fetch(
        {"instrument_code": "gold1", "trade_date": "2026-08-01", "min_price": "100", "max_price": "2000", "is_canceled": 0, "data_source": "tsetmc"},
        offset=0,
        limit=50,
    )
    assert total == 5
    assert rows == [{"instrument_code": "gold1", "price": 1000}]
    mock_count.assert_awaited_once()
    mock_get.assert_awaited_once()
