from typing import Any

from sqladmin import ModelView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from sqlmodel import select

from src.admin._render import _parse_int
from src.admin.market_data import MarketDataListView
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


class GoldOrderBookView(MarketDataListView):
    resolve_instrument_code = staticmethod(_resolve_instrument_code)
    table_name = "stock_order_book"
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

    @expose("/gold-order-book", methods=["GET"])
    async def gold_order_book_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class GoldTradesView(MarketDataListView):
    resolve_instrument_code = staticmethod(_resolve_instrument_code)
    table_name = "stock_trades"
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

    @expose("/gold-trades", methods=["GET"])
    async def gold_trades_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)
