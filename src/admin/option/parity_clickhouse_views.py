from typing import Any

from sqladmin import expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_date, _parse_int
from src.admin._views import ClickHouseListView
from src.db.clickhouse.parity import (
    count_snapshots,
    get_snapshots_paginated,
)


class ParityAnalysisSnapshotsView(ClickHouseListView):
    template_name = "option/parity_snapshots_list.html"
    page_title = "Parity Analysis Snapshots"
    page_subtitle = "Browse aligned quotes, calculated edges, and data-quality results"
    name = "Parity Snapshots"
    identity = "parity-analysis-snapshots"
    icon = "fa-solid fa-camera"
    category = "Options Analytics"
    category_icon = "fa-solid fa-chart-line"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "run_id": qp.get("run_id", ""),
            "trade_date": qp.get("trade_date", ""),
            "underlying_instrument_code": qp.get("underlying_instrument_code", ""),
            "quality_status": qp.get("quality_status", ""),
            "opportunity": _parse_int(qp.get("opportunity")),
        }

    async def fetch(self, filters, offset, limit) -> tuple[int, list[dict]]:
        trade_date = _parse_date(filters["trade_date"]) if filters["trade_date"] else None
        kwargs = {
            "run_id": filters["run_id"] or None,
            "trade_date": trade_date,
            "underlying_instrument_code": filters["underlying_instrument_code"] or None,
            "quality_status": filters["quality_status"] or None,
            "opportunity": filters["opportunity"],
        }
        total = await count_snapshots(**kwargs)
        rows = await get_snapshots_paginated(**kwargs, offset=offset, limit=limit)
        return total, rows

    @expose("/parity-analysis-snapshots", methods=["GET"])
    async def parity_analysis_snapshots(self, request: Request) -> HTMLResponse:
        return await self._list(request)
