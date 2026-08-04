from typing import Any

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.services.operation_runs import enqueue_task
from src.tasks import (
    backfill_bond_order_books_task,
    backfill_bond_trades_task,
    backfill_option_order_books_task,
    backfill_option_trades_task,
    backfill_stock_order_books_task,
    backfill_stock_trades_task,
    backfill_yield_curves,
    compute_yield_curve_snapshot,
    sync_bond_instruments,
    sync_option_instruments,
    sync_stock_instruments,
)


class CeleryTasksView(BaseView):
    name = "Background Tasks"
    identity = "celery-tasks"
    icon = "fa-solid fa-tasks"
    category = "Operations"
    category_icon = "fa-solid fa-gears"

    @expose("/celery-tasks", methods=["GET", "POST"])
    async def celery_tasks(self, request: Request) -> HTMLResponse:
        messages: list[dict[str, str]] = []

        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            tasks = {
                "sync-bond-instruments": sync_bond_instruments,
                "sync-option-instruments": sync_option_instruments,
                "sync-stock-instruments": sync_stock_instruments,
                "backfill-bond-order-books": backfill_bond_order_books_task,
                "backfill-bond-trades": backfill_bond_trades_task,
                "backfill-stock-order-books": backfill_stock_order_books_task,
                "backfill-stock-trades": backfill_stock_trades_task,
                "backfill-option-order-books": backfill_option_order_books_task,
                "backfill-option-trades": backfill_option_trades_task,
                "compute-yield-curve": compute_yield_curve_snapshot,
                "backfill-yield-curves": backfill_yield_curves,
            }
            task = tasks.get(action)
            if task is None:
                messages.append({"type": "danger", "text": f"Unknown action: {action}"})
            else:
                kwargs = {}
                if action.startswith("backfill-"):
                    kwargs = {
                        "start_date_str": str(form.get("start_date") or ""),
                        "end_date_str": str(form.get("end_date") or ""),
                    }
                row, async_result = enqueue_task(
                    task,
                    kwargs=kwargs,
                    trigger="manual",
                    created_by=request.session.get("user") or "admin",
                )
                page = "/admin/yield-curve-runs" if row.family == "yield_curve" else "/admin/collection-runs"
                messages.append({
                    "type": "success",
                    "text": (
                        f'Run <code>{row.run_id}</code> queued as task <code>{async_result.id}</code>. '
                        f'<a href="{page}?run_id={row.run_id}">View run</a>'
                    ),
                })

        ctx: dict[str, Any] = {
            "request": request,
            "admin": self._admin_ref,
            "title": "Admin Tasks",
            "subtitle": "Trigger and monitor Celery tasks",
            "messages": messages,
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("shared/admin_tasks.html", ctx))
