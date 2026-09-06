from sqladmin import BaseView, expose
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.admin.run_views import OperationRunsView


class GoldKalmanView(BaseView):
    name = "Gold Kalman Monitor"
    identity = "gold-kalman"
    icon = "fa-solid fa-wave-square"
    category = "Gold Analytics"

    @expose("/gold-kalman", methods=["GET"])
    async def monitor(self, request):
        return HTMLResponse(_render("gold/kalman.html", {
            "request": request, "admin": self._admin_ref,
            "url_for": lambda name, **kw: request.url_for(name, **kw),
            "title": self.name, "subtitle": "Relative gold ETF value • historical replay • prices in IRR",
        }))


class GoldKalmanRunsView(OperationRunsView):
    name = "Gold Kalman Runs"
    identity = "gold-kalman-runs"
    icon = "fa-solid fa-list-check"
    category = "Gold Analytics"
    family = "gold_kalman"
    page_title = "Gold Kalman Runs"
    page_subtitle = "Frozen policies, progress, calibration and evaluation results"

    @expose("/gold-kalman-runs", methods=["GET"])
    async def history(self, request):
        return await self._runs(request)
