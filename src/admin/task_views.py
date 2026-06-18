import html

from celery.result import AsyncResult
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.celery_app import celery
from src.tasks import (
    backfill_order_books_task,
    sync_bond_instruments,
)


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{title}</title></head>
<body><div class="container-fluid">{body}</div></body>
</html>"""


def _danger(text: str) -> str:
    return f'<div class="alert alert-danger">{html.escape(text)}</div>'


def _success(text: str) -> str:
    return f'<div class="alert alert-success">{html.escape(text)}</div>'


def _info(text: str) -> str:
    return f'<div class="alert alert-info">{html.escape(text)}</div>'


def _backfill_form(start_date: str, end_date: str) -> str:
    safe_start = html.escape(start_date)
    safe_end = html.escape(end_date)
    return f"""<form method="post" action="/admin/celery-tasks" class="mb-3">
<input type="hidden" name="action" value="backfill">
<div class="row g-2 mb-2">
<div class="col-auto"><input type="date" class="form-control" name="start_date" value="{safe_start}" required></div>
<div class="col-auto"><input type="date" class="form-control" name="end_date" value="{safe_end}" required></div>
<div class="col-auto"><button type="submit" class="btn btn-warning">Backfill Order Books</button></div>
</div></form>"""


def _task_status_form() -> str:
    return """<form method="post" action="/admin/celery-tasks" class="mb-3">
<input type="hidden" name="action" value="check-status">
<div class="row g-2 mb-2">
<div class="col-auto"><input type="text" class="form-control" name="task_id" placeholder="Task ID" required style="width:300px"></div>
<div class="col-auto"><button type="submit" class="btn btn-info">Check Status</button></div>
</div></form>"""


class CeleryTasksView(BaseView):
    name = "Tasks"
    identity = "celery-tasks"
    icon = "fa-solid fa-tasks"

    @expose("/celery-tasks", methods=["GET", "POST"])
    async def celery_tasks(self, request: Request) -> HTMLResponse:
        body = "<h1>Admin Tasks</h1>"

        if request.method == "POST":
            form = await request.form()
            action = form.get("action")

            if action == "sync-instruments":
                task = sync_bond_instruments.delay()
                body += _success(f"Task submitted: <code>{html.escape(task.id)}</code> (status: {task.status})")

            elif action == "backfill":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                task = backfill_order_books_task.delay(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                )
                body += _success(f"Task submitted: <code>{html.escape(task.id)}</code> (status: {task.status})")

            elif action == "check-status":
                task_id = form.get("task_id", "")
                if not task_id:
                    body += _danger("No task ID provided")
                else:
                    async_result = AsyncResult(task_id, app=celery)
                    state = async_result.status
                    if async_result.successful():
                        result = async_result.result
                        if isinstance(result, dict):
                            parts = [f"{k}={v}" for k, v in result.items()]
                            body += _success(f"Task <code>{html.escape(task_id)}</code>: {state}<br>{'<br>'.join(parts)}")
                        else:
                            body += _success(f"Task <code>{html.escape(task_id)}</code>: {state}<br>{html.escape(str(result))}")
                    elif async_result.failed():
                        body += _danger(f"Task <code>{html.escape(task_id)}</code>: {state}<br>{html.escape(str(async_result.result))}")
                    else:
                        body += _info(f"Task <code>{html.escape(task_id)}</code>: {state}")
            else:
                body += _danger(f"Unknown action: {html.escape(str(action))}")

        body += _info("Tasks run asynchronously on the Celery worker. Submit a task above, then use the status checker below to see the result.")
        body += "<hr><h3>Sync Instruments</h3>"
        body += """<p>Fetch bond instrument metadata from TSETMC and upsert into PostgreSQL.</p>
<form method="post" action="/admin/celery-tasks" class="mb-4">
<input type="hidden" name="action" value="sync-instruments">
<button type="submit" class="btn btn-primary">Sync Instruments</button>
</form>"""

        body += "<hr><h3>Backfill Order Books</h3>"
        body += "<p>Fetch historical order book snapshots from TSETMC for the given date range.</p>"
        body += _backfill_form("", "")

        body += "<hr><h3>Task Status</h3>"
        body += "<p>Check the status and result of a submitted task.</p>"
        body += _task_status_form()

        return HTMLResponse(_page("Admin Tasks", body))