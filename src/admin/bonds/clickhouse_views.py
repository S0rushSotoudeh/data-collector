from typing import Any

from sqladmin import expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_int
from src.admin.market_data import MarketDataListView


class BondOrderBookView(MarketDataListView):
    table_name = "bond_order_book"
    template_name = "bonds/order_book_list.html"
    page_title = "Bond Order Book"
    page_subtitle = "Browse and filter order book snapshots"
    name = "Bond Order Book"
    identity = "order-book"
    icon = "fa-solid fa-book"
    category = "Bond Market"
    category_icon = "fa-solid fa-landmark"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "depth_level": _parse_int(qp.get("depth_level")),
            "data_source": qp.get("data_source", ""),
        }

    @expose("/order-book", methods=["GET"])
    async def order_book_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class BondTradesView(MarketDataListView):
    table_name = "bond_trades"
    template_name = "bonds/trades_list.html"
    page_title = "Bond Trades"
    page_subtitle = "Browse and filter trade records"
    name = "Bond Trades"
    identity = "trades"
    icon = "fa-solid fa-chart-line"
    category = "Bond Market"
    category_icon = "fa-solid fa-landmark"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "min_price": qp.get("min_price", ""),
            "max_price": qp.get("max_price", ""),
            "is_canceled": _parse_int(qp.get("is_canceled")),
            "data_source": qp.get("data_source", ""),
        }

    @expose("/trades", methods=["GET"])
    async def trades_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)
