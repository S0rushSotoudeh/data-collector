from typing import Any

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.services.operation_runs import enqueue_task
from src.db.models.ime import ImeProducer
from src.db.session import SessionLocal
from sqlmodel import select
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
    sync_gold_instruments,
    backfill_gold_order_books_task,
    backfill_gold_trades_task,
    sync_ime_producers,
    backfill_ime_physical_trades,
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
        with SessionLocal() as session:
            ime_producers = list(
                session.execute(
                    select(ImeProducer).where(ImeProducer.enabled.is_(True)).order_by(ImeProducer.name)
                ).scalars()
            )

        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            tasks = {
                "sync-bond-instruments": sync_bond_instruments,
                "sync-option-instruments": sync_option_instruments,
                "sync-stock-instruments": sync_stock_instruments,
                "sync-gold-instruments": sync_gold_instruments,
                "backfill-bond-order-books": backfill_bond_order_books_task,
                "backfill-bond-trades": backfill_bond_trades_task,
                "backfill-stock-order-books": backfill_stock_order_books_task,
                "backfill-stock-trades": backfill_stock_trades_task,
                "backfill-gold-order-books": backfill_gold_order_books_task,
                "backfill-gold-trades": backfill_gold_trades_task,
                "backfill-option-order-books": backfill_option_order_books_task,
                "backfill-option-trades": backfill_option_trades_task,
                "compute-yield-curve": compute_yield_curve_snapshot,
                "backfill-yield-curves": backfill_yield_curves,
                "sync-ime-producers": sync_ime_producers,
                "backfill-ime-physical-trades": backfill_ime_physical_trades,
            }
            task = tasks.get(action)
            if task is None:
                messages.append({"type": "danger", "text": f"Unknown action: {action}"})
            else:
                kwargs = {}
                validation_error = ""
                if action == "backfill-ime-physical-trades":
                    try:
                        producer_code = int(str(form.get("producer_code") or "0"))
                    except ValueError:
                        producer_code = 0
                    allowed = {item.producer_code for item in ime_producers}
                    all_history = str(form.get("all_history") or "").lower() in {"1", "true", "on"}
                    start_value = str(form.get("start_date") or "")
                    end_value = str(form.get("end_date") or "")
                    if producer_code not in allowed:
                        validation_error = "Select an enabled IME producer."
                    try:
                        from datetime import date
                        from src.collectors.ime.service import ALL_HISTORY_START
                        start = ALL_HISTORY_START if all_history else date.fromisoformat(start_value)
                        end = date.today() if all_history and not end_value else date.fromisoformat(end_value)
                        if start > end:
                            validation_error = "Start date must not be after end date."
                    except ValueError:
                        validation_error = "Valid start and end dates are required."
                    kwargs = {
                        "producer_code": producer_code,
                        "start_date_str": start.isoformat() if not validation_error else start_value,
                        "end_date_str": end.isoformat() if not validation_error else end_value,
                        "all_history": all_history,
                    }
                elif action.startswith("backfill-"):
                    kwargs = {
                        "start_date_str": str(form.get("start_date") or ""),
                        "end_date_str": str(form.get("end_date") or ""),
                    }
                if validation_error:
                    messages.append({"type": "danger", "text": validation_error})
                else:
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
            "ime_producers": ime_producers,
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("shared/admin_tasks.html", ctx))
