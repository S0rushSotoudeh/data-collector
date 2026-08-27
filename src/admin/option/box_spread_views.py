from typing import Any

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render


class BoxCalculatorView(BaseView):
    name = "Box Calculator"
    identity = "options-box-calculator"
    icon = "fa-solid fa-calculator"
    category = "Options Analytics"
    category_icon = "fa-solid fa-chart-line"

    @expose("/options-box-calculator", methods=["GET"])
    async def options_box_calculator(self, request: Request) -> HTMLResponse:
        ctx: dict[str, Any] = {
            "request": request, "admin": self._admin_ref,
            "url_for": lambda name, **kw: request.url_for(name, **kw),
            "title": "Box Calculator",
            "subtitle": "One maker, three takers — historical executable economics",
        }
        return HTMLResponse(_render("option/box_calculator.html", ctx))


class BoxSpreadView(BaseView):
    name = "Box-Spread Mispricing"
    identity = "options-box-spread"
    icon = "fa-solid fa-cubes-stacked"
    category = "Options Analytics"
    category_icon = "fa-solid fa-chart-line"

    @expose("/options-box-spread", methods=["GET"])
    async def options_box_spread(self, request: Request) -> HTMLResponse:
        ctx: dict[str, Any] = {
            "request": request, "admin": self._admin_ref,
            "url_for": lambda name, **kw: request.url_for(name, **kw),
            "title": "Box-Spread Implied-Rate Anomalies",
            "subtitle": "Historical five-level executable pricing with eight one-maker hedge cases",
        }
        return HTMLResponse(_render("option/box_spread.html", ctx))
