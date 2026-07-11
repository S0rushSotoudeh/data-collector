from typing import Any

from celery.result import AsyncResult
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.celery_app import celery
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
            action = form.get("action")

            if action == "sync-bond-instruments":
                task = sync_bond_instruments.delay()
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "backfill-bond-order-books":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_bond_order_books_task.delay(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                )
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "backfill-bond-trades":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_bond_trades_task.delay(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                )
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "backfill-stock-order-books":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_stock_order_books_task.delay(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                )
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "sync-option-instruments":
                task = sync_option_instruments.delay()
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "sync-stock-instruments":
                task = sync_stock_instruments.delay()
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "backfill-option-order-books":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_option_order_books_task.delay(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                )
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "backfill-option-trades":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_option_trades_task.delay(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                )
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "backfill-stock-trades":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_stock_trades_task.delay(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                )
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "compute-yield-curve":
                task = compute_yield_curve_snapshot.delay()
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "backfill-yield-curves":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_yield_curves.delay(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                )
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "check-status":
                task_id = form.get("task_id", "")
                if not task_id:
                    messages.append({"type": "danger", "text": "No task ID provided"})
                else:
                    async_result = AsyncResult(task_id, app=celery)
                    state = async_result.status
                    if async_result.successful():
                        result = async_result.result
                        if isinstance(result, dict):
                            parts = "<br>".join(f"{k}={v}" for k, v in result.items())
                            messages.append({
                                "type": "success",
                                "text": f'Task <code>{task_id}</code>: {state}<br>{parts}',
                            })
                        else:
                            messages.append({
                                "type": "success",
                                "text": f'Task <code>{task_id}</code>: {state}<br>{result}',
                            })
                    elif async_result.failed():
                        messages.append({
                            "type": "danger",
                            "text": f'Task <code>{task_id}</code>: {state}<br>{async_result.result}',
                        })
                    else:
                        messages.append({
                            "type": "info",
                            "text": f'Task <code>{task_id}</code>: {state}',
                        })
            else:
                messages.append({"type": "danger", "text": f"Unknown action: {action}"})

        ctx: dict[str, Any] = {
            "request": request,
            "admin": self._admin_ref,
            "title": "Admin Tasks",
            "subtitle": "Trigger and monitor Celery tasks",
            "messages": messages,
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("admin_tasks.html", ctx))
