from pathlib import Path
from typing import Any

import jinja2
import sqladmin
from celery.result import AsyncResult
from sqladmin import BaseView, expose
from sqladmin.flash import get_flashed_messages
from sqladmin.secret import Secret
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.celery_app import celery
from src.tasks import (
    backfill_order_books_task,
    backfill_trades_task,
    sync_bond_instruments,
)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_SQLADMIN_TEMPLATE_DIR = Path(sqladmin.__file__).parent / "templates"
_TEMPLATE_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader([str(_TEMPLATE_DIR), str(_SQLADMIN_TEMPLATE_DIR)]),
    autoescape=True,
    auto_reload=False,
)
_TEMPLATE_ENV.globals["get_flashed_messages"] = get_flashed_messages
_TEMPLATE_ENV.globals["Secret"] = Secret
_TEMPLATE_ENV.globals["min"] = min
_TEMPLATE_ENV.globals["zip"] = zip


def _render(name: str, ctx: dict[str, Any]) -> str:
    return _TEMPLATE_ENV.get_template(name).render(ctx)


class CeleryTasksView(BaseView):
    name = "Tasks"
    identity = "celery-tasks"
    icon = "fa-solid fa-tasks"

    @expose("/celery-tasks", methods=["GET", "POST"])
    async def celery_tasks(self, request: Request) -> HTMLResponse:
        messages: list[dict[str, str]] = []

        if request.method == "POST":
            form = await request.form()
            action = form.get("action")

            if action == "sync-instruments":
                task = sync_bond_instruments.delay()
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "backfill":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_order_books_task.delay(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                )
                messages.append({
                    "type": "success",
                    "text": f'Task submitted: <code>{task.id}</code> (status: {task.status})',
                })

            elif action == "backfill-trades":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_trades_task.delay(
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