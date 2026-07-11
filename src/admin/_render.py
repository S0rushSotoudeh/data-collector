import html
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from typing import Any

import jinja2
import sqladmin
from sqladmin.flash import get_flashed_messages
from sqladmin.secret import Secret
from starlette.responses import HTMLResponse

_PAGE_SIZE = 100

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_SQLADMIN_TEMPLATE_DIR = Path(sqladmin.__file__).parent / "templates"
_TEMPLATE_ENV = jinja2.Environment(
    loader=jinja2.ChoiceLoader(
        [
            jinja2.FileSystemLoader([str(_TEMPLATE_DIR), str(_SQLADMIN_TEMPLATE_DIR)]),
            # ``sqladmin/layout.html`` is overridden locally.  The override
            # extends this alias to retain SQLAdmin's original layout.
            jinja2.PrefixLoader(
                {
                    "sqladmin_original": jinja2.FileSystemLoader(
                        str(_SQLADMIN_TEMPLATE_DIR / "sqladmin")
                    )
                }
            ),
        ]
    ),
    autoescape=True,
    auto_reload=False,
)
_TEMPLATE_ENV.globals["get_flashed_messages"] = get_flashed_messages
_TEMPLATE_ENV.globals["Secret"] = Secret
_TEMPLATE_ENV.globals["min"] = min
_TEMPLATE_ENV.globals["zip"] = zip


def _render(name: str, ctx: dict[str, Any]) -> str:
    return _TEMPLATE_ENV.get_template(name).render(ctx)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _parse_page(raw: str | None) -> int:
    if not raw:
        return 1
    try:
        return max(1, int(raw))
    except (ValueError, TypeError):
        return 1


def _qs_page(params: dict[str, str], page: int) -> str:
    qs = dict(params)
    qs["page"] = str(page)
    return urlencode(qs)


def _error_response(e: Exception) -> HTMLResponse:
    return HTMLResponse(
        f"<html><body><h2>Error</h2><p>{html.escape(str(e))}</p></body></html>",
        status_code=500,
    )
