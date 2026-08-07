from typing import Any

from sqlalchemy import select
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.db.models.operations import OptionPricingConvention
from src.db.session import SessionLocal


class OptionMispricingView(BaseView):
    name = "Mispricing Scanner"
    identity = "options-mispricing"
    icon = "fa-solid fa-magnifying-glass-chart"
    category = "Options Analytics"
    category_icon = "fa-solid fa-chart-line"

    @expose("/options-mispricing", methods=["GET"])
    async def options_mispricing(self, request: Request) -> HTMLResponse:
        with SessionLocal() as session:
            conventions = session.execute(
                select(OptionPricingConvention).where(
                    OptionPricingConvention.approved.is_(True),
                    OptionPricingConvention.black76_compatible.is_(True),
                ).order_by(OptionPricingConvention.name)
            ).scalars().all()
        ctx: dict[str, Any] = {
            "request": request, "admin": self._admin_ref,
            "url_for": lambda name, **kw: request.url_for(name, **kw),
            "title": "Date-Driven Option Mispricing Scanner",
            "subtitle": "Market-wide historical ORC fair values, rankings, and underlying drill-down",
            "conventions": conventions,
        }
        return HTMLResponse(_render("option/mispricing.html", ctx))
