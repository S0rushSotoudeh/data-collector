from typing import Any

from sqladmin import expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_date, _parse_int
from src.admin._views import ClickHouseListView
from src.db.clickhouse import price_to_storage
from src.db.clickhouse.query import (
    get_order_book_paginated,
    count_order_book,
    get_trades_paginated,
    count_trades,
)


class BondOrderBookView(ClickHouseListView):
    template_name = "order_book_list.html"
    page_title = "Bond Order Book"
    page_subtitle = "Browse and filter order book snapshots"
    name = "Order Book"
    identity = "order-book"
    icon = "fa-solid fa-book"

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
        total = await count_order_book(
            instrument_code=instrument_code,
            trade_date=trade_date,
            depth_level=depth_level,
            data_source=data_source,
        )
        rows = await get_order_book_paginated(
            instrument_code=instrument_code,
            trade_date=trade_date,
            depth_level=depth_level,
            data_source=data_source,
            offset=offset,
            limit=limit,
        )
        return total, rows

    @expose("/order-book", methods=["GET"])
    async def order_book_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class BondTradesView(ClickHouseListView):
    template_name = "trades_list.html"
    page_title = "Bond Trades"
    page_subtitle = "Browse and filter trade records"
    name = "Trades"
    identity = "trades"
    icon = "fa-solid fa-chart-line"

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
        total = await count_trades(
            instrument_code=instrument_code,
            trade_date=trade_date,
            min_price=min_price,
            max_price=max_price,
            is_canceled=is_canceled,
            data_source=data_source,
        )
        rows = await get_trades_paginated(
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

    @expose("/trades", methods=["GET"])
    async def trades_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)
