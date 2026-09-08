from unittest.mock import AsyncMock, patch

from sqladmin import Admin
from starlette.applications import Starlette
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
    admin = Admin(Starlette())
    admin.add_base_view(GoldOrderBookView)
    admin.add_base_view(GoldTradesView)
    assert GoldInstrumentAdmin.category == "Gold Market"
    assert GoldInstrumentAdmin.identity == "gold-instrument"
    assert GoldOrderBookView.category == "Gold Market"
    assert GoldOrderBookView.identity == "gold_order_book_list"
    assert GoldTradesView.category == "Gold Market"
    assert GoldTradesView.identity == "gold_trades_list"


@patch("src.admin.gold.views._resolve_instrument_code", return_value="123")
@patch("src.admin.market_data.market_data_page", new_callable=AsyncMock)
async def test_gold_order_book_fetch(mock_get, mock_resolve) -> None:
    mock_get.return_value = [{"instrument_code": "gold1"}]

    view = GoldOrderBookView()
    with patch.object(view, "resolve_instrument_code", mock_resolve):
        rows = await view.fetch_rows(
            {"instrument_code": "gold1", "trade_date": "2026-08-01", "depth_level": 1, "data_source": "tsetmc"},
        )
    assert rows == [{"instrument_code": "gold1"}]
    mock_get.assert_awaited_once()
    assert mock_get.call_args.args[1]["instrument_code"] == "123"
    assert mock_get.call_args.args[-1] == 101


@patch("src.admin.gold.views._resolve_instrument_code", return_value="123")
@patch("src.admin.market_data.market_data_page", new_callable=AsyncMock)
async def test_gold_trades_fetch(mock_get, mock_resolve) -> None:
    mock_get.return_value = [{"instrument_code": "gold1", "price": 1000}]

    view = GoldTradesView()
    with patch.object(view, "resolve_instrument_code", mock_resolve):
        rows = await view.fetch_rows(
            {"instrument_code": "gold1", "trade_date": "2026-08-01", "min_price": "100", "max_price": "2000", "is_canceled": 0, "data_source": "tsetmc"},
        )
    assert rows == [{"instrument_code": "gold1", "price": 1000}]
    mock_get.assert_awaited_once()
    filters = mock_get.call_args.args[1]
    assert filters["instrument_code"] == "123"
    assert (filters["min_price"], filters["max_price"], filters["is_canceled"]) == (100, 2000, 0)
