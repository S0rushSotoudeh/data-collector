import html
from datetime import date
from typing import Any

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.db.clickhouse import get_async_client
from src.db.clickhouse.query import (
    get_latest_order_book,
    get_latest_order_books,
    get_latest_trades,
    get_trade_history,
)
from src.db.clickhouse.schema import ORDER_BOOK_COLUMNS, TRADES_COLUMNS

_OB_HEADERS = [c for c in ORDER_BOOK_COLUMNS if c != "ingested_at"]
_TR_HEADERS = [c for c in TRADES_COLUMNS if c != "ingested_at"]

_OB_ROW_TPL = "<td>{" + "}</td><td>{".join(_OB_HEADERS) + "}</td>"
_TR_ROW_TPL = "<td>{" + "}</td><td>{".join(_TR_HEADERS) + "}</td>"

_MAX_LIMIT = 5000


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{title}</title></head>
<body><div class="container-fluid">{body}</div></body>
</html>"""


def _table(headers: list[str], rows: list[dict[str, Any]], row_tpl: str) -> str:
    h = "".join(f"<th>{c}</th>" for c in headers)
    r = "".join(f"<tr>{row_tpl.format(**row)}</tr>" for row in rows)
    return f"<table class='table table-striped table-hover'><thead><tr>{h}</tr></thead><tbody>{r}</tbody></table>"


def _parse_limit(raw: str | None, default: int = 10) -> int:
    if raw is None:
        return default
    try:
        val = int(raw)
        if val < 1:
            return default
        if val > _MAX_LIMIT:
            return _MAX_LIMIT
        return val
    except (ValueError, TypeError):
        return default


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _search_form(
    action: str,
    instrument_code: str,
    trade_date_str: str,
) -> str:
    safe_code = html.escape(instrument_code)
    safe_date = html.escape(trade_date_str)
    return f"""<form method="get" action="{html.escape(action)}" class="mb-3">
<div class="row g-2">
<div class="col-auto"><input type="text" class="form-control" name="instrument_code" placeholder="Instrument Code" value="{safe_code}"></div>
<div class="col-auto"><input type="date" class="form-control" name="trade_date" value="{safe_date}"></div>
<div class="col-auto"><button type="submit" class="btn btn-primary">Search</button></div>
</div></form>"""


def _danger(text: str) -> str:
    return f'<div class="alert alert-danger">{html.escape(text)}</div>'


class BondOrderBookView(BaseView):
    name = "Order Book"
    identity = "order-book"
    icon = "fa-solid fa-book"

    @expose("/order-book", methods=["GET"])
    async def order_book(self, request: Request) -> HTMLResponse:
        error = None
        rows = []
        instrument_code = request.query_params.get("instrument_code", "")
        trade_date_str = request.query_params.get("trade_date", "")
        dt = _parse_date(trade_date_str)

        if instrument_code and dt:
            try:
                rows = await get_latest_order_book(instrument_code, dt)
            except Exception as e:
                error = str(e)
        elif instrument_code and not dt:
            error = "Invalid trade_date"
        elif not instrument_code:
            error = "instrument_code + trade_date required"

        body = "<h1>Bond Order Book</h1>"
        if error:
            body += _danger(error)
        body += _search_form("/admin/order-book", instrument_code, trade_date_str)
        if rows:
            body += _table(_OB_HEADERS, rows, _OB_ROW_TPL)
        body += '<br><a href="/admin/order-book/latest" class="btn btn-secondary">Latest Snapshots</a>'
        return HTMLResponse(_page("Bond Order Book", body))

    @expose("/order-book/latest", methods=["GET"])
    async def order_book_latest(self, request: Request) -> HTMLResponse:
        error = None
        rows = []
        limit = _parse_limit(request.query_params.get("limit"), 10)
        try:
            rows = await get_latest_order_books(limit=limit)
        except Exception as e:
            error = str(e)

        body = "<h1>Latest Order Book Snapshots</h1>"
        if error:
            body += _danger(error)
        if rows:
            body += _table(_OB_HEADERS, rows, _OB_ROW_TPL)
        return HTMLResponse(_page("Latest Order Book", body))


class BondTradesView(BaseView):
    name = "Trades"
    identity = "trades"
    icon = "fa-solid fa-chart-line"

    @expose("/trades", methods=["GET"])
    async def trades(self, request: Request) -> HTMLResponse:
        error = None
        rows = []
        instrument_code = request.query_params.get("instrument_code", "")
        trade_date_str = request.query_params.get("trade_date", "")
        limit = _parse_limit(request.query_params.get("limit"), 500)
        dt = _parse_date(trade_date_str)

        if instrument_code and dt:
            try:
                rows = await get_trade_history(instrument_code, dt, limit=limit)
            except Exception as e:
                error = str(e)
        elif instrument_code and not dt:
            error = "Invalid trade_date"
        elif not instrument_code:
            error = "instrument_code + trade_date required"

        body = "<h1>Bond Trades</h1>"
        if error:
            body += _danger(error)
        body += _search_form("/admin/trades", instrument_code, trade_date_str)
        if rows:
            body += _table(_TR_HEADERS, rows, _TR_ROW_TPL)
        body += '<br><a href="/admin/trades/latest" class="btn btn-secondary">Latest Trades</a>'
        return HTMLResponse(_page("Bond Trades", body))

    @expose("/trades/latest", methods=["GET"])
    async def trades_latest(self, request: Request) -> HTMLResponse:
        error = None
        rows = []
        limit = _parse_limit(request.query_params.get("limit"), 10)
        try:
            rows = await get_latest_trades(limit=limit)
        except Exception as e:
            error = str(e)

        body = "<h1>Latest Trades</h1>"
        if error:
            body += _danger(error)
        if rows:
            body += _table(_TR_HEADERS, rows, _TR_ROW_TPL)
        return HTMLResponse(_page("Latest Trades", body))