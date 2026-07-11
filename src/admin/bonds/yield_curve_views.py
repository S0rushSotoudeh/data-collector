from typing import Any

from sqladmin import expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_date, _parse_int
from src.admin._views import ClickHouseListView
from src.db.clickhouse.query import (
    count_yield_curve_fits,
    get_yield_curve_fits_paginated,
    count_yield_curve_bonds,
    get_yield_curve_bonds_paginated,
)


class YieldCurveFitsView(ClickHouseListView):
    template_name = "bonds/yield_curve_fits_list.html"
    page_title = "Yield Curve Fits"
    page_subtitle = "Browse Nelson-Siegel fit snapshots"
    name = "Bond Yield Curve Fits"
    identity = "yield-curve-fits"
    icon = "fa-solid fa-chart-area"
    category = "Bond Analytics"
    category_icon = "fa-solid fa-chart-area"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "trade_date": qp.get("trade_date", ""),
            "curve_side": qp.get("curve_side", ""),
            "converged": _parse_int(qp.get("converged")),
        }

    async def fetch(self, filters, offset, limit) -> tuple[int, list[dict]]:
        trade_date_str = filters["trade_date"]
        trade_date = _parse_date(trade_date_str) if trade_date_str else None
        curve_side = filters["curve_side"]
        converged = filters["converged"]
        total = await count_yield_curve_fits(
            trade_date=trade_date,
            curve_side=curve_side,
            converged=converged,
        )
        rows = await get_yield_curve_fits_paginated(
            trade_date=trade_date,
            curve_side=curve_side,
            converged=converged,
            offset=offset,
            limit=limit,
        )
        return total, rows

    @expose("/yield-curve-fits", methods=["GET"])
    async def yield_curve_fits_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class YieldCurveBondsView(ClickHouseListView):
    template_name = "bonds/yield_curve_bonds_list.html"
    page_title = "Yield Curve Bonds"
    page_subtitle = "Browse per-bond yield curve points"
    name = "Bond Yield Curve Points"
    identity = "yield-curve-bonds"
    icon = "fa-solid fa-link"
    category = "Bond Analytics"
    category_icon = "fa-solid fa-chart-area"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "trade_date": qp.get("trade_date", ""),
            "trade_time": _parse_int(qp.get("trade_time")),
            "instrument_code": qp.get("instrument_code", ""),
            "curve_side": qp.get("curve_side", ""),
            "symbol": qp.get("symbol", ""),
        }

    async def fetch(self, filters, offset, limit) -> tuple[int, list[dict]]:
        trade_date_str = filters["trade_date"]
        trade_date = _parse_date(trade_date_str) if trade_date_str else None
        trade_time = filters["trade_time"]
        instrument_code = filters["instrument_code"] or None
        curve_side = filters["curve_side"]
        symbol = filters["symbol"] or None
        total = await count_yield_curve_bonds(
            trade_date=trade_date,
            trade_time=trade_time,
            instrument_code=instrument_code,
            curve_side=curve_side,
            symbol=symbol,
        )
        rows = await get_yield_curve_bonds_paginated(
            trade_date=trade_date,
            trade_time=trade_time,
            instrument_code=instrument_code,
            curve_side=curve_side,
            symbol=symbol,
            offset=offset,
            limit=limit,
        )
        return total, rows

    @expose("/yield-curve-bonds", methods=["GET"])
    async def yield_curve_bonds_list(self, request: Request) -> HTMLResponse:
        return await self._list(request)
