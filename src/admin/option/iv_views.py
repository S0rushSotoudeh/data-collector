from typing import Any

from sqlalchemy import select
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.db.models.operations import OptionPricingConvention
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal


class OptionsMarketPotentialView(BaseView):
    name = "Market Potential"
    identity = "options-market-potential"
    icon = "fa-solid fa-bullseye"
    category = "Options Analytics"
    category_icon = "fa-solid fa-chart-line"

    @expose("/options-market-potential", methods=["GET"])
    async def options_market_potential(self, request: Request) -> HTMLResponse:
        ctx: dict[str, Any] = {
            "request": request, "admin": self._admin_ref,
            "url_for": lambda name, **kw: request.url_for(name, **kw),
            "title": "Options Market Potential",
            "subtitle": "Activity, liquidity, concentration, coverage, and pilot-ready packages",
        }
        return HTMLResponse(_render("option/market_potential.html", ctx))


class IVSurfaceView(BaseView):
    name = "ORC Wing IV"
    identity = "options-iv-surface"
    icon = "fa-solid fa-wave-square"
    category = "Options Analytics"
    category_icon = "fa-solid fa-chart-line"

    @expose("/options-iv-surface", methods=["GET"])
    async def options_iv_surface(self, request: Request) -> HTMLResponse:
        with SessionLocal() as session:
            stocks = session.execute(select(StockInstrument).order_by(StockInstrument.symbol)).scalars().all()
            conventions = session.execute(
                select(OptionPricingConvention).where(
                    OptionPricingConvention.approved.is_(True),
                    OptionPricingConvention.black76_compatible.is_(True),
                ).order_by(OptionPricingConvention.name)
            ).scalars().all()
        ctx: dict[str, Any] = {
            "request": request, "admin": self._admin_ref,
            "url_for": lambda name, **kw: request.url_for(name, **kw),
            "title": "Historical Executable IV & ORC Wing",
            "subtitle": "Admin-triggered replay with independent executable bid and ask surfaces",
            "stocks": stocks, "conventions": conventions,
        }
        return HTMLResponse(_render("option/iv_surface.html", ctx))
