import html
from datetime import date

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from src.collectors.bond.instrument_sync import sync_instruments_to_pg
from src.collectors.bond.order_book_fetcher import (
    backfill_order_books,
    get_instrument_codes_active_in_range,
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
                try:
                    result = await sync_instruments_to_pg()
                    msg = f"Synced {result['synced']} instruments"
                    if result["errors"]:
                        msg += f" with {len(result['errors'])} error(s)"
                        for e in result["errors"]:
                            msg += f"<br>&nbsp;&nbsp;{html.escape(str(e))}"
                        body += _danger(msg)
                    else:
                        body += _success(msg)
                except Exception as e:
                    body += _danger(f"Sync failed: {e}")

            elif action == "backfill":
                start_date_str = form.get("start_date", "")
                end_date_str = form.get("end_date", "")
                try:
                    start_date = date.fromisoformat(start_date_str)
                    end_date = date.fromisoformat(end_date_str)
                except (ValueError, TypeError):
                    body += _danger("Invalid date format")
                    body += _backfill_form(start_date_str, end_date_str)
                    return HTMLResponse(_page("Admin Tasks", body))

                try:
                    codes = await get_instrument_codes_active_in_range(
                        start_date, end_date
                    )
                    result = await backfill_order_books(
                        start_date=start_date,
                        end_date=end_date,
                        instrument_codes=codes,
                    )
                    msg = (
                        f"Backfill complete: {result['total_days_tried']} day(s), "
                        f"{result['total_rows']} rows, "
                        f"{len(codes)} instrument(s)"
                    )
                    if result["errors"]:
                        for e in result["errors"]:
                            msg += f"<br>&nbsp;&nbsp;{html.escape(str(e))}"
                        body += _danger(msg)
                    else:
                        body += _success(msg)
                except Exception as e:
                    body += _danger(f"Backfill failed: {e}")

            else:
                body += _danger(f"Unknown action: {html.escape(str(action))}")

        body += _info("Trigger background tasks manually. Tasks run synchronously in this request.")
        body += """<hr><h3>Sync Instruments</h3>
<p>Fetch bond instrument metadata from TSETMC and upsert into PostgreSQL.</p>
<form method="post" action="/admin/celery-tasks" class="mb-4">
<input type="hidden" name="action" value="sync-instruments">
<button type="submit" class="btn btn-primary">Sync Instruments</button>
</form>"""

        body += "<hr><h3>Backfill Order Books</h3>"
        body += "<p>Fetch historical order book snapshots from TSETMC for the given date range.</p>"
        body += _backfill_form("", "")

        return HTMLResponse(_page("Admin Tasks", body))
