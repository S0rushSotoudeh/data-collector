from typing import Any

from sqlalchemy import select
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.db.models.option import OptionInstrument
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal


class OptionsAnalyticsView(BaseView):
    name = "Put–Call Parity"
    identity = "options-parity"
    icon = "fa-solid fa-scale-balanced"
    category = "Options Analytics"
    category_icon = "fa-solid fa-chart-line"

    @expose("/options-parity", methods=["GET"])
    async def options_parity(self, request: Request) -> HTMLResponse:
        with SessionLocal() as session:
            stocks = session.execute(
                select(StockInstrument).order_by(StockInstrument.symbol)
            ).scalars().all()
            options = session.execute(
                select(OptionInstrument).order_by(OptionInstrument.expiry_date, OptionInstrument.symbol)
            ).scalars().all()
        instruments = [{
            "code": item.instrument_code, "symbol": item.symbol or item.instrument_code,
            "type": (item.option_type or "").lower(), "strike": float(item.strike_price) if item.strike_price else None,
            "expiry": item.expiry_date.isoformat() if item.expiry_date else None,
            "underlying": item.underlying_instrument_code,
        } for item in options]
        ctx: dict[str, Any] = {
            "request": request, "admin": self._admin_ref,
            "url_for": lambda name, **kw: request.url_for(name, **kw),
            "title": "Put–Call Parity Analysis",
            "subtitle": "Immutable 30-second executable-liquidity snapshots",
            "stocks": stocks, "options": instruments,
        }
        return HTMLResponse(_render("option/parity_analysis.html", ctx))
