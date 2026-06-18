from datetime import date
from math import ceil
from pathlib import Path
from urllib.parse import urlencode
from typing import Any

import jinja2
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.db.clickhouse import price_to_storage
from src.db.clickhouse.query import (
    get_order_book_paginated,
    count_order_book,
    get_trades_paginated,
    count_trades,
)

_PAGE_SIZE = 100

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_TEMPLATE_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
    auto_reload=False,
)


def _render(name: str, ctx: dict[str, Any]) -> str:
    return _TEMPLATE_ENV.get_template(name).render(ctx)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _qs_page(
    params: dict[str, str],
    page: int,
) -> str:
    qs = dict(params)
    qs["page"] = str(page)
    return urlencode(qs)


class BondOrderBookView(BaseView):
    name = "Order Book"
    identity = "order-book"
    icon = "fa-solid fa-book"

    @expose("/order-book", methods=["GET"])
    async def order_book_list(self, request: Request) -> HTMLResponse:
        qp = dict(request.query_params)

        instrument_code = qp.get("instrument_code", "") or None
        trade_date_str = qp.get("trade_date", "") or None
        trade_date = _parse_date(trade_date_str)
        depth_level = _parse_int(qp.get("depth_level")) if qp.get("depth_level") else None
        data_source = qp.get("data_source", "") or None
        page_raw = qp.get("page", "1")
        page = 1
        try:
            page = max(1, int(page_raw))
        except (ValueError, TypeError):
            page = 1

        offset = (page - 1) * _PAGE_SIZE

        try:
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
                limit=_PAGE_SIZE,
            )
        except Exception as e:
            return HTMLResponse(f"<html><body><h2>Error</h2><p>{e}</p></body></html>", status_code=500)

        total_pages = max(1, ceil(total / _PAGE_SIZE))

        ctx: dict[str, Any] = {
            "request": request,
            "title": "Bond Order Book",
            "subtitle": "Browse and filter order book snapshots",
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": _PAGE_SIZE,
            "total_pages": total_pages,
            "instrument_code": instrument_code or "",
            "trade_date": trade_date_str or "",
            "depth_level": depth_level,
            "data_source": data_source or "",
            "qs_page": lambda p: _qs_page(qp, p),
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("order_book_list.html", ctx))


class BondTradesView(BaseView):
    name = "Trades"
    identity = "trades"
    icon = "fa-solid fa-chart-line"

    @expose("/trades", methods=["GET"])
    async def trades_list(self, request: Request) -> HTMLResponse:
        qp = dict(request.query_params)

        instrument_code = qp.get("instrument_code", "") or None
        trade_date_str = qp.get("trade_date", "") or None
        trade_date = _parse_date(trade_date_str)
        data_source = qp.get("data_source", "") or None
        page_raw = qp.get("page", "1")
        page = 1
        try:
            page = max(1, int(page_raw))
        except (ValueError, TypeError):
            page = 1

        min_price_raw = qp.get("min_price") or None
        max_price_raw = qp.get("max_price") or None
        min_price = None
        max_price = None
        if min_price_raw is not None:
            min_price = price_to_storage(min_price_raw)
        if max_price_raw is not None:
            max_price = price_to_storage(max_price_raw)

        is_canceled_raw = qp.get("is_canceled") or None
        is_canceled = _parse_int(is_canceled_raw)

        offset = (page - 1) * _PAGE_SIZE

        try:
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
                limit=_PAGE_SIZE,
            )
        except Exception as e:
            return HTMLResponse(f"<html><body><h2>Error</h2><p>{e}</p></body></html>", status_code=500)

        total_pages = max(1, ceil(total / _PAGE_SIZE))
        ctx: dict[str, Any] = {
            "request": request,
            "title": "Bond Trades",
            "subtitle": "Browse and filter trade records",
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": _PAGE_SIZE,
            "total_pages": total_pages,
            "instrument_code": instrument_code or "",
            "trade_date": trade_date_str or "",
            "data_source": data_source or "",
            "min_price": qp.get("min_price", ""),
            "max_price": qp.get("max_price", ""),
            "is_canceled": _parse_int(is_canceled_raw),
            "qs_page": lambda p: _qs_page(qp, p),
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("trades_list.html", ctx))