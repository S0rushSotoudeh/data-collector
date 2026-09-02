from typing import Any

from sqladmin import ModelView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from sqlmodel import select

from src.admin._render import _parse_date, _parse_int
from src.admin._views import ClickHouseListView
from src.db.clickhouse import price_to_storage
from src.db.clickhouse.stock import (
    count_stock_order_book,
    count_stock_trades,
    get_stock_order_book_paginated,
    get_stock_trades_paginated,
)
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal


def _resolve_instrument_code(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return raw
    normalized = raw.replace("ی", "ي").replace("ک", "ك")
    with SessionLocal() as session:
        inst = (
            session.execute(
                select(StockInstrument).where(
                    (StockInstrument.symbol == raw)
                    | (StockInstrument.symbol == normalized)
                    | (StockInstrument.symbol.ilike(f"%{raw}%"))
                    | (StockInstrument.symbol.ilike(f"%{normalized}%"))
                )
            )
            .scalars()
            .first()
        )
        if inst:
            return inst.instrument_code
    return raw


class GoldInstrumentAdmin(ModelView, model=StockInstrument):
    name = "Gold Instrument"
    name_plural = "Gold Instruments"
    identity = "gold-instrument"
    icon = "fa-solid fa-coins"
    category = "Gold Market"
    category_icon = "fa-solid fa-coins"
    column_list = [
        StockInstrument.instrument_code,
        StockInstrument.symbol,
        StockInstrument.name_fa,
        StockInstrument.status,
        StockInstrument.security_type_name,
        StockInstrument.last_trade_date,
        StockInstrument.created_at,
    ]
    column_searchable_list = [
        StockInstrument.instrument_code,
        StockInstrument.symbol,
        StockInstrument.name_fa,
        StockInstrument.name_en,
        StockInstrument.isin,
    ]
    column_sortable_list = [
        StockInstrument.instrument_code,
        StockInstrument.symbol,
        StockInstrument.status,
        StockInstrument.last_trade_date,
        StockInstrument.security_type_code,
        StockInstrument.created_at,
    ]
    column_default_sort = [(StockInstrument.symbol, False)]
    can_create = False
    can_edit = True
    can_delete = False
    can_export = True
    page_size = 50

    def list_query(self, request: Request) -> Any:
        return super().list_query(request).filter(StockInstrument.is_gold_etf.is_(True))

    def count_query(self, request: Request) -> Any:
        return super().count_query(request).filter(StockInstrument.is_gold_etf.is_(True))


GoldInstrumentAdmin.identity = "gold-instrument"


class GoldOrderBookView(ClickHouseListView):
    template_name = "gold/gold_order_book_list.html"
    page_title = "Gold ETF Order Book"
    page_subtitle = "Browse and filter gold ETF order book snapshots"
    name = "Gold Order Book"
    identity = "gold-order-book"
    icon = "fa-solid fa-book-open-reader"
    category = "Gold Market"
    category_icon = "fa-solid fa-coins"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "depth_level": _parse_int(qp.get("depth_level")),
            "data_source": qp.get("data_source", ""),
        }

    async def fetch(self, filters: dict[str, Any], offset: int, limit: int) -> tuple[int, list[dict]]:
        instrument_code = _resolve_instrument_code(filters["instrument_code"])
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

    @expose("/gold-order-book", methods=["GET"])
    async def gold_order_book_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class GoldTradesView(ClickHouseListView):
    template_name = "gold/gold_trades_list.html"
    page_title = "Gold ETF Trades"
    page_subtitle = "Browse and filter gold ETF trade records"
    name = "Gold Trades"
    identity = "gold-trades"
    icon = "fa-solid fa-arrow-trend-up"
    category = "Gold Market"
    category_icon = "fa-solid fa-coins"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "instrument_code": qp.get("instrument_code", ""),
            "trade_date": qp.get("trade_date", ""),
            "min_price": qp.get("min_price", ""),
            "max_price": qp.get("max_price", ""),
            "is_canceled": _parse_int(qp.get("is_canceled")),
            "data_source": qp.get("data_source", ""),
        }

    async def fetch(self, filters: dict[str, Any], offset: int, limit: int) -> tuple[int, list[dict]]:
        instrument_code = _resolve_instrument_code(filters["instrument_code"])
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

    @expose("/gold-trades", methods=["GET"])
    async def gold_trades_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)
