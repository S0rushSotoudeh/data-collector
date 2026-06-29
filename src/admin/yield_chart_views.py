from typing import Any

from sqladmin import BaseView, expose
from sqlmodel import select
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.db.models.bond import BondInstrument
from src.db.session import SessionLocal


class YieldCurveChartView(BaseView):
    name = "Yield Curve Chart"
    identity = "yield-curve-chart"
    icon = "fa-solid fa-bezier-curve"

    @expose("/yield-curve-chart", methods=["GET"])
    async def yield_curve_chart(self, request: Request) -> HTMLResponse:
        ctx: dict[str, Any] = {
            "request": request,
            "admin": self._admin_ref,
            "title": "Yield Curve Chart",
            "subtitle": "Term structure scatter + Nelson-Siegel fit",
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("yield_curve_chart.html", ctx))


class YieldSpreadChartView(BaseView):
    name = "Yield Spread Chart"
    identity = "yield-spread-chart"
    icon = "fa-solid fa-arrows-left-right"

    @expose("/yield-spread-chart", methods=["GET"])
    async def yield_spread_chart(self, request: Request) -> HTMLResponse:
        instruments: list[dict[str, str]] = []
        with SessionLocal() as session:
            stmt = select(BondInstrument).order_by(BondInstrument.symbol.asc())
            bonds = session.execute(stmt).scalars().all()
            for b in bonds:
                instruments.append({
                    "instrument_code": b.instrument_code,
                    "symbol": b.symbol or b.instrument_code,
                })

        ctx: dict[str, Any] = {
            "request": request,
            "admin": self._admin_ref,
            "title": "Yield Spread Chart",
            "subtitle": "Per-instrument NS spread residual",
            "instruments": instruments,
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("yield_spread_chart.html", ctx))
