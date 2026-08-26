from __future__ import annotations

import json
from math import ceil
from typing import Any

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import (
    _PAGE_SIZE,
    _error_response,
    _parse_date,
    _parse_page,
    _qs_page,
    _render,
)
from src.services.operation_runs import RUN_STATUSES, list_runs, run_to_dict


class OperationRunsView(BaseView):
    family: str
    page_title: str
    page_subtitle: str

    async def _runs(self, request: Request) -> HTMLResponse:
        qp = dict(request.query_params)
        page = _parse_page(qp.get("page"))
        filters = {
            "run_id": qp.get("run_id", ""),
            "run_type": qp.get("run_type", ""),
            "status": qp.get("status", ""),
            "created_from": qp.get("created_from", ""),
            "created_to": qp.get("created_to", ""),
        }
        try:
            total, stored = list_runs(
                family=self.family,
                run_id=filters["run_id"] or None,
                run_type=filters["run_type"] or None,
                status=filters["status"] or None,
                start_date=_parse_date(filters["created_from"]),
                end_date=_parse_date(filters["created_to"]),
                offset=(page - 1) * _PAGE_SIZE,
                limit=_PAGE_SIZE,
            )
        except Exception as exc:
            return _error_response(exc)
        rows: list[dict[str, Any]] = []
        for item in stored:
            row = run_to_dict(item)
            started = item.started_at or item.created_at
            finished = item.completed_at
            row["duration"] = "—"
            if started and finished:
                seconds = max(0, int((finished - started).total_seconds()))
                row["duration"] = f"{seconds // 60}m {seconds % 60}s" if seconds >= 60 else f"{seconds}s"
            row["config_pretty"] = json.dumps(item.config or {}, ensure_ascii=False, indent=2, default=str)
            row["result_pretty"] = json.dumps(item.result or {}, ensure_ascii=False, indent=2, default=str)
            row["detail_url"] = None
            row["detail_label"] = None
            if self.family == "parity":
                row["detail_url"] = f"/admin/parity-analysis-snapshots?run_id={item.run_id}"
                row["detail_label"] = "Snapshots"
            elif self.family == "box_spread":
                row["detail_url"] = f"/admin/options-box-spread?run_id={item.run_id}"
                row["detail_label"] = "Visualization"
            elif self.family == "iv_orc":
                row["detail_url"] = f"/admin/options-iv-surface?run_id={item.run_id}"
                row["detail_label"] = "Visualization"
            elif self.family == "option_mispricing":
                row["detail_url"] = f"/admin/options-mispricing?run_id={item.run_id}"
                row["detail_label"] = "Ranking"
            elif self.family == "collection" and item.target == "ime_physical_trades":
                producer_code = (item.config or {}).get("producer_code")
                suffix = f"?producer_code={producer_code}" if producer_code else ""
                row["detail_url"] = f"/admin/ime-price-volume{suffix}"
                row["detail_label"] = "Chart"
            rows.append(row)
        total_pages = max(1, ceil(total / _PAGE_SIZE))
        ctx = {
            "request": request,
            "admin": self._admin_ref,
            "url_for": lambda name, **kw: request.url_for(name, **kw),
            "title": self.page_title,
            "subtitle": self.page_subtitle,
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": _PAGE_SIZE,
            "total_pages": total_pages,
            "statuses": RUN_STATUSES,
            "qs_page": lambda value: _qs_page(qp, value),
            **filters,
        }
        return HTMLResponse(_render("operations/run_list.html", ctx))


class CollectionRunsView(OperationRunsView):
    name = "Collection Runs"
    identity = "collection-runs"
    icon = "fa-solid fa-database"
    category = "Operations"
    category_icon = "fa-solid fa-gears"
    family = "collection"
    page_title = "Collection Runs"
    page_subtitle = "Instrument sync, scheduled collection, and historical backfill executions"

    @expose("/collection-runs", methods=["GET"])
    async def collection_runs(self, request: Request) -> HTMLResponse:
        return await self._runs(request)


class YieldCurveRunsView(OperationRunsView):
    name = "Yield-Curve Runs"
    identity = "yield-curve-runs"
    icon = "fa-solid fa-chart-line"
    category = "Bond Analytics"
    family = "yield_curve"
    page_title = "Yield-Curve Runs"
    page_subtitle = "Scheduled snapshots and historical yield-curve backfills"

    @expose("/yield-curve-runs", methods=["GET"])
    async def yield_curve_runs(self, request: Request) -> HTMLResponse:
        return await self._runs(request)


class MarketPotentialRunsView(OperationRunsView):
    name = "Market-Potential Runs"
    identity = "market-potential-runs"
    icon = "fa-solid fa-bullseye"
    category = "Options Analytics"
    family = "market_potential"
    page_title = "Market-Potential Runs"
    page_subtitle = "Daily option market-potential computations"

    @expose("/market-potential-runs", methods=["GET"])
    async def market_potential_runs(self, request: Request) -> HTMLResponse:
        return await self._runs(request)


class ParityRunsView(OperationRunsView):
    name = "Parity Runs"
    identity = "parity-analysis-runs"
    icon = "fa-solid fa-list-check"
    category = "Options Analytics"
    family = "parity"
    page_title = "Parity Runs"
    page_subtitle = "Immutable put-call parity configurations and execution outcomes"

    @expose("/parity-analysis-runs", methods=["GET"])
    async def parity_runs(self, request: Request) -> HTMLResponse:
        return await self._runs(request)


class IVORCRunsView(OperationRunsView):
    name = "IV/ORC Runs"
    identity = "iv-orc-runs"
    icon = "fa-solid fa-wave-square"
    category = "Options Analytics"
    family = "iv_orc"
    page_title = "IV/ORC Runs"
    page_subtitle = "Executable IV calculation and ORC Wing fitting as one tracked pipeline"

    @expose("/iv-orc-runs", methods=["GET"])
    async def iv_orc_runs(self, request: Request) -> HTMLResponse:
        return await self._runs(request)


class BoxSpreadRunsView(OperationRunsView):
    name = "Box-Spread Runs"
    identity = "box-spread-runs"
    icon = "fa-solid fa-list-check"
    category = "Options Analytics"
    family = "box_spread"
    page_title = "Box-Spread Runs"
    page_subtitle = "Immutable focused-pair implied-rate replays and their execution classifications"

    @expose("/box-spread-runs", methods=["GET"])
    async def box_spread_runs(self, request: Request) -> HTMLResponse:
        return await self._runs(request)


class OptionMispricingRunsView(OperationRunsView):
    name = "Mispricing Runs"
    identity = "option-mispricing-runs"
    icon = "fa-solid fa-ranking-star"
    category = "Options Analytics"
    family = "option_mispricing"
    page_title = "Option Mispricing Runs"
    page_subtitle = "Immutable market-wide date-driven ORC valuation scans"

    @expose("/option-mispricing-runs", methods=["GET"])
    async def option_mispricing_runs(self, request: Request) -> HTMLResponse:
        return await self._runs(request)
