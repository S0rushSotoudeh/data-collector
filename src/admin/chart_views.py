from typing import Any

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render


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
