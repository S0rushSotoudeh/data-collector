from typing import Any

from sqladmin import expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_int
from src.admin.market_data import MarketDataListView


class StockOrderBookView(MarketDataListView):
    table_name = "stock_order_book"
    template_name = "stock/stock_order_book_list.html"
    page_title = "Stock Order Book"
    page_subtitle = "Browse and filter stock order book snapshots"
    name = "Stock Order Book"
    identity = "stock-order-book"
    icon = "fa-solid fa-book-open-reader"
    category = "Stock Market"
    category_icon = "fa-solid fa-chart-line"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "depth_level": _parse_int(qp.get("depth_level")),
            "data_source": qp.get("data_source", ""),
        }

    @expose("/stock-order-book", methods=["GET"])
    async def stock_order_book_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class StockTradesView(MarketDataListView):
    table_name = "stock_trades"
    template_name = "stock/stock_trades_list.html"
    page_title = "Stock Trades"
    page_subtitle = "Browse and filter stock trade records"
    name = "Stock Trades"
    identity = "stock-trades"
    icon = "fa-solid fa-arrow-trend-up"
    category = "Stock Market"
    category_icon = "fa-solid fa-chart-line"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "min_price": qp.get("min_price", ""),
            "max_price": qp.get("max_price", ""),
            "is_canceled": _parse_int(qp.get("is_canceled")),
            "data_source": qp.get("data_source", ""),
        }

    @expose("/stock-trades", methods=["GET"])
    async def stock_trades_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)
