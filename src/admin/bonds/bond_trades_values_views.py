from typing import Any

from sqladmin import BaseView, expose
from sqlmodel import select
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.db.models.bond import BondInstrument
from src.db.session import SessionLocal


class BondTradesValuesChartView(BaseView):
    name = "Bond Trade Values"
    identity = "bond-trades-values-chart"
    icon = "fa-solid fa-chart-column"
    category = "Bond Analytics"
    category_icon = "fa-solid fa-chart-area"

    @expose("/bond-trades-values-chart", methods=["GET"])
    async def bond_trades_values_chart(self, request: Request) -> HTMLResponse:
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
            "title": "Bond Trades Values",
            "subtitle": "Per-instrument trade price / value",
            "instruments": instruments,
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("bonds/bond_trades_values.html", ctx))


class BondTradesRankingChartView(BaseView):
    name = "Bond Trades Ranking"
    identity = "bond-trades-ranking"
    icon = "fa-solid fa-ranking-star"
    category = "Bond Analytics"
    category_icon = "fa-solid fa-chart-area"

    @expose("/bond-trades-ranking", methods=["GET"])
    async def bond_trades_ranking(self, request: Request) -> HTMLResponse:
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
            "title": "Bond Trades Ranking",
            "subtitle": "Rank all bonds by total trading value over a date range",
            "instruments": instruments,
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("bonds/bond_trades_ranking.html", ctx))
