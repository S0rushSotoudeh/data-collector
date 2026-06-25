from math import ceil
from typing import Any

from sqladmin import BaseView
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import (
    _PAGE_SIZE,
    _error_response,
    _parse_page,
    _qs_page,
    _render,
)


class ClickHouseListView(BaseView):
    template_name: str
    page_title: str
    page_subtitle: str

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError

    async def fetch(self, filters, offset, limit) -> tuple[int, list[dict]]:
        raise NotImplementedError

    async def _list(self, request: Request) -> HTMLResponse:
        qp = dict(request.query_params)
        page = _parse_page(qp.get("page"))
        offset = (page - 1) * _PAGE_SIZE
        try:
            filters = self.parse_filters(qp)
            total, rows = await self.fetch(filters, offset, _PAGE_SIZE)
        except Exception as e:
            return _error_response(e)
        total_pages = max(1, ceil(total / _PAGE_SIZE))
        ctx: dict[str, Any] = {
            "request": request,
            "admin": self._admin_ref,
            "title": self.page_title,
            "subtitle": self.page_subtitle,
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": _PAGE_SIZE,
            "total_pages": total_pages,
            "qs_page": lambda p: _qs_page(qp, p),
            "url_for": lambda n, **kw: request.url_for(n, **kw),
        }
        ctx.update(filters)
        return HTMLResponse(_render(self.template_name, ctx))
