from typing import Any

from sqladmin import expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_date, _parse_int
from src.admin._views import ClickHouseListView
from src.db.clickhouse.iv_surface import (
    count_iv_points,
    count_orc_wing_fits,
    get_iv_points_paginated,
    get_orc_wing_fits_paginated,
)


class OptionIVPointsView(ClickHouseListView):
    template_name = "option/iv_points_list.html"
    page_title = "Executable IV Points"
    page_subtitle = "Browse accepted and rejected executable bid/ask IV observations"
    name = "Executable IV Points"
    identity = "option-iv-points"
    icon = "fa-solid fa-table-list"
    category = "Options Analytics"
    category_icon = "fa-solid fa-chart-line"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "run_id": qp.get("run_id", ""),
            "trade_date": qp.get("trade_date", ""),
            "underlying_instrument_code": qp.get("underlying_instrument_code", ""),
            "instrument_code": qp.get("instrument_code", ""),
            "option_type": qp.get("option_type", ""),
            "side": qp.get("side", ""),
            "expiry_date": qp.get("expiry_date", ""),
            "rejection_reason": qp.get("rejection_reason", ""),
        }

    async def fetch(self, filters, offset, limit) -> tuple[int, list[dict]]:
        rejection_filter = filters["rejection_reason"]
        kwargs = {
            "run_id": filters["run_id"] or None,
            "trade_date": _parse_date(filters["trade_date"]) if filters["trade_date"] else None,
            "underlying_instrument_code": filters["underlying_instrument_code"] or None,
            "instrument_code": filters["instrument_code"] or None,
            "option_type": filters["option_type"] or None,
            "side": filters["side"] or None,
            "expiry_date": _parse_date(filters["expiry_date"]) if filters["expiry_date"] else None,
            "rejection_reason": "" if rejection_filter == "__valid__" else rejection_filter or None,
        }
        total = await count_iv_points(**kwargs)
        rows = await get_iv_points_paginated(**kwargs, offset=offset, limit=limit)
        return total, rows

    @expose("/option-iv-points", methods=["GET"])
    async def option_iv_points(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class ORCWingFitsView(ClickHouseListView):
    template_name = "option/orc_wing_fits_list.html"
    page_title = "ORC Wing Fits"
    page_subtitle = "Browse fitted bid/ask surfaces, parameters, convergence, and quality flags"
    name = "ORC Wing Fits"
    identity = "orc-wing-fits"
    icon = "fa-solid fa-wave-square"
    category = "Options Analytics"
    category_icon = "fa-solid fa-chart-line"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        return {
            "run_id": qp.get("run_id", ""),
            "trade_date": qp.get("trade_date", ""),
            "underlying_instrument_code": qp.get("underlying_instrument_code", ""),
            "expiry_date": qp.get("expiry_date", ""),
            "side": qp.get("side", ""),
            "converged": _parse_int(qp.get("converged")),
            "quality_flag": qp.get("quality_flag", ""),
        }

    async def fetch(self, filters, offset, limit) -> tuple[int, list[dict]]:
        kwargs = {
            "run_id": filters["run_id"] or None,
            "trade_date": _parse_date(filters["trade_date"]) if filters["trade_date"] else None,
            "underlying_instrument_code": filters["underlying_instrument_code"] or None,
            "expiry_date": _parse_date(filters["expiry_date"]) if filters["expiry_date"] else None,
            "side": filters["side"] or None,
            "converged": filters["converged"],
            "quality_flag": filters["quality_flag"] or None,
        }
        total = await count_orc_wing_fits(**kwargs)
        rows = await get_orc_wing_fits_paginated(**kwargs, offset=offset, limit=limit)
        return total, rows

    @expose("/orc-wing-fits", methods=["GET"])
    async def orc_wing_fits(self, request: Request) -> HTMLResponse:
        return await self._list(request)
