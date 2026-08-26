from __future__ import annotations

from typing import Any

from sqladmin import BaseView, ModelView, expose
from sqlmodel import select
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_date, _parse_int, _render
from src.admin._views import ClickHouseListView
from src.db.clickhouse.ime import count_ime_trades, get_ime_trades_paginated
from src.db.models.ime import ImeProducer, ImeProduct
from src.db.session import SessionLocal


class ImeProducerAdmin(ModelView, model=ImeProducer):
    name = "IME Producer"
    name_plural = "IME Producers"
    icon = "fa-solid fa-industry"
    category = "IME Physical Market"
    category_icon = "fa-solid fa-warehouse"
    column_list = [
        ImeProducer.producer_code, ImeProducer.name, ImeProducer.enabled,
        ImeProducer.synced_at, ImeProducer.updated_at,
    ]
    column_searchable_list = [ImeProducer.name]
    column_sortable_list = [ImeProducer.producer_code, ImeProducer.name, ImeProducer.enabled]
    column_default_sort = [(ImeProducer.name, False)]
    form_columns = [ImeProducer.enabled]
    can_create = False
    can_edit = True
    can_delete = False
    can_export = True
    page_size = 50


class ImeProductAdmin(ModelView, model=ImeProduct):
    name = "IME Product"
    name_plural = "IME Products"
    icon = "fa-solid fa-boxes-stacked"
    category = "IME Physical Market"
    category_icon = "fa-solid fa-warehouse"
    column_list = [
        ImeProduct.producer_code, ImeProduct.symbol, ImeProduct.goods_name,
        ImeProduct.unit, ImeProduct.currency, ImeProduct.last_trade_date,
    ]
    column_searchable_list = [ImeProduct.symbol, ImeProduct.goods_name]
    column_sortable_list = [ImeProduct.producer_code, ImeProduct.symbol, ImeProduct.last_trade_date]
    column_default_sort = [(ImeProduct.last_trade_date, True)]
    can_create = False
    can_edit = False
    can_delete = False
    can_export = True
    page_size = 50


class ImeTradesView(ClickHouseListView):
    template_name = "ime/trades_list.html"
    page_title = "IME Physical Trades"
    page_subtitle = "Browse physical-market price and volume rows"
    name = "IME Trades"
    identity = "ime-physical-trades"
    icon = "fa-solid fa-table-list"
    category = "IME Physical Market"
    category_icon = "fa-solid fa-warehouse"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "producer_code": _parse_int(qp.get("producer_code")),
            "product_symbol": qp.get("product_symbol", ""),
            "trade_date": qp.get("trade_date", ""),
            "contract_type": qp.get("contract_type", ""),
        }

    async def fetch(self, filters, offset, limit) -> tuple[int, list[dict]]:
        trade_date = _parse_date(filters["trade_date"]) if filters["trade_date"] else None
        kwargs = {
            "producer_code": filters["producer_code"],
            "product_symbol": filters["product_symbol"] or None,
            "trade_date": trade_date,
            "contract_type": filters["contract_type"] or None,
        }
        total = await count_ime_trades(**kwargs)
        rows = await get_ime_trades_paginated(**kwargs, offset=offset, limit=limit)
        return total, rows

    @expose("/ime-physical-trades", methods=["GET"])
    async def ime_trades(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class ImePriceVolumeView(BaseView):
    name = "IME Price & Volume"
    identity = "ime-price-volume"
    icon = "fa-solid fa-chart-line"
    category = "IME Physical Market"
    category_icon = "fa-solid fa-warehouse"

    @expose("/ime-price-volume", methods=["GET"])
    async def ime_price_volume(self, request: Request) -> HTMLResponse:
        with SessionLocal() as session:
            producers = list(
                session.execute(
                    select(ImeProducer)
                    .where(ImeProducer.enabled.is_(True))
                    .order_by(ImeProducer.name)
                ).scalars()
            )
        selected = _parse_int(request.query_params.get("producer_code"))
        ctx: dict[str, Any] = {
            "request": request,
            "admin": self._admin_ref,
            "url_for": lambda name, **params: request.url_for(name, **params),
            "title": "IME Price & Volume",
            "subtitle": "Site-reported closing price and traded volume per contract row",
            "producers": producers,
            "selected_producer_code": selected,
        }
        return HTMLResponse(_render("ime/price_volume.html", ctx))
