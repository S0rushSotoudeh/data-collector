from typing import Any

from sqladmin import expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_date, _parse_int
from src.admin._views import ClickHouseListView
from src.db.clickhouse import price_to_storage
from src.db.clickhouse.stock import (
    count_stock_order_book,
    count_stock_trades,
    get_stock_order_book_paginated,
    get_stock_trades_paginated,
)


class StockOrderBookView(ClickHouseListView):
    template_name = "stock_order_book_list.html"
    page_title = "Stock Order Book"
    page_subtitle = "Browse and filter stock order book snapshots"
    name = "Stock Order Book"
    identity = "stock-order-book"
    icon = "fa-solid fa-book-open-reader"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "depth_level": _parse_int(qp.get("depth_level")),
            "data_source": qp.get("data_source", ""),
        }

    async def fetch(self, filters, offset, limit) -> tuple[int, list[dict]]:
        instrument_code = filters["instrument_code"] or None
        trade_date_str = filters["trade_date"]
        trade_date = _parse_date(trade_date_str) if trade_date_str else None
        depth_level = filters["depth_level"]
        data_source = filters["data_source"] or None
        total = await count_stock_order_book(
            instrument_code=instrument_code,
            trade_date=trade_date,
            depth_level=depth_level,
            data_source=data_source,
        )
        rows = await get_stock_order_book_paginated(
            instrument_code=instrument_code,
            trade_date=trade_date,
            depth_level=depth_level,
            data_source=data_source,
            offset=offset,
            limit=limit,
        )
        return total, rows

    @expose("/stock-order-book", methods=["GET"])
    async def stock_order_book_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class StockTradesView(ClickHouseListView):
    template_name = "stock_trades_list.html"
    page_title = "Stock Trades"
    page_subtitle = "Browse and filter stock trade records"
    name = "Stock Trades"
    identity = "stock-trades"
    icon = "fa-solid fa-arrow-trend-up"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "min_price": qp.get("min_price", ""),
            "max_price": qp.get("max_price", ""),
            "is_canceled": _parse_int(qp.get("is_canceled")),
            "data_source": qp.get("data_source", ""),
        }

    async def fetch(self, filters, offset, limit) -> tuple[int, list[dict]]:
        instrument_code = filters["instrument_code"] or None
        trade_date_str = filters["trade_date"]
        trade_date = _parse_date(trade_date_str) if trade_date_str else None
        min_price_raw = filters["min_price"]
        max_price_raw = filters["max_price"]
        min_price = price_to_storage(min_price_raw) if min_price_raw else None
        max_price = price_to_storage(max_price_raw) if max_price_raw else None
        is_canceled = filters["is_canceled"]
        data_source = filters["data_source"] or None
        total = await count_stock_trades(
            instrument_code=instrument_code,
            trade_date=trade_date,
            min_price=min_price,
            max_price=max_price,
            is_canceled=is_canceled,
            data_source=data_source,
        )
        rows = await get_stock_trades_paginated(
            instrument_code=instrument_code,
            trade_date=trade_date,
            min_price=min_price,
            max_price=max_price,
            is_canceled=is_canceled,
            data_source=data_source,
            offset=offset,
            limit=limit,
        )
        return total, rows

    @expose("/stock-trades", methods=["GET"])
    async def stock_trades_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)
