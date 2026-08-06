from typing import Any

from sqladmin import expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_date, _parse_int
from src.admin._views import ClickHouseListView
from src.db.clickhouse.box_spread import (
    count_pricings, count_snapshots, get_pricings_paginated, get_snapshots_paginated,
)


class BoxSpreadSnapshotsView(ClickHouseListView):
    template_name = "option/box_spread_snapshots_list.html"
    page_title = "Box-Spread Snapshots"
    page_subtitle = "Coherent four-leg depth summaries, benchmark curve, and quality diagnostics"
    name = "Box Snapshots"
    identity = "box-spread-snapshots"
    icon = "fa-solid fa-camera"
    category = "Options Analytics"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "run_id": qp.get("run_id", ""), "trade_date": qp.get("trade_date", ""),
            "underlying_instrument_code": qp.get("underlying_instrument_code", ""),
            "quality_status": qp.get("quality_status", ""),
        }

    async def fetch(self, filters, offset, limit):
        kwargs = {
            "run_id": filters["run_id"] or None,
            "trade_date": _parse_date(filters["trade_date"]) if filters["trade_date"] else None,
            "underlying_instrument_code": filters["underlying_instrument_code"] or None,
            "quality_status": filters["quality_status"] or None,
        }
        return await count_snapshots(**kwargs), await get_snapshots_paginated(**kwargs, offset=offset, limit=limit)

    @expose("/box-spread-snapshots", methods=["GET"])
    async def box_spread_snapshots(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class BoxSpreadPricingsView(ClickHouseListView):
    template_name = "option/box_spread_pricings_list.html"
    page_title = "Box-Spread Pricings"
    page_subtitle = "Direct executable boxes and one-maker/three-taker quote cases"
    name = "Box Pricings"
    identity = "box-spread-pricings"
    icon = "fa-solid fa-scale-balanced"
    category = "Options Analytics"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "run_id": qp.get("run_id", ""), "trade_date": qp.get("trade_date", ""),
            "direction": qp.get("direction", ""), "execution_mode": qp.get("execution_mode", ""),
            "classification": qp.get("classification", ""), "opportunity": _parse_int(qp.get("opportunity")),
        }

    async def fetch(self, filters, offset, limit):
        kwargs = {
            "run_id": filters["run_id"] or None,
            "trade_date": _parse_date(filters["trade_date"]) if filters["trade_date"] else None,
            "direction": filters["direction"] or None, "execution_mode": filters["execution_mode"] or None,
            "classification": filters["classification"] or None, "opportunity": filters["opportunity"],
        }
        return await count_pricings(**kwargs), await get_pricings_paginated(**kwargs, offset=offset, limit=limit)

    @expose("/box-spread-pricings", methods=["GET"])
    async def box_spread_pricings(self, request: Request) -> HTMLResponse:
        return await self._list(request)
