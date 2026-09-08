from typing import Any

from sqladmin import expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_int
from src.admin.market_data import MarketDataListView


class OptionOrderBookView(MarketDataListView):
    table_name = "option_order_book"
    template_name = "option/option_order_book_list.html"
    page_title = "Option Order Book"
    page_subtitle = "Browse and filter option order book snapshots"
    name = "Option Order Book"
    identity = "option-order-book"
    icon = "fa-solid fa-book-open"
    category = "Options Market"
    category_icon = "fa-solid fa-file-contract"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "depth_level": _parse_int(qp.get("depth_level")),
            "data_source": qp.get("data_source", ""),
        }

    @expose("/option-order-book", methods=["GET"])
    async def option_order_book_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class OptionTradesView(MarketDataListView):
    table_name = "option_trades"
    template_name = "option/option_trades_list.html"
    page_title = "Option Trades"
    page_subtitle = "Browse and filter option trade records"
    name = "Option Trades"
    identity = "option-trades"
    icon = "fa-solid fa-chart-line"
    category = "Options Market"
    category_icon = "fa-solid fa-file-contract"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "min_price": qp.get("min_price", ""),
            "max_price": qp.get("max_price", ""),
            "is_canceled": _parse_int(qp.get("is_canceled")),
            "data_source": qp.get("data_source", ""),
        }

    @expose("/option-trades", methods=["GET"])
    async def option_trades_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)
