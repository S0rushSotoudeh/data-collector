from __future__ import annotations

import csv
import io
import json
import math
import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import StreamingResponse

from src.analytics.iv import MODEL_VERSION, WingParameters, orc_wing
from src.analytics.iv_config import IVSurfaceRunConfig
from src.analytics.parity_engine import aligned_snapshots
from src.db.clickhouse.iv_surface import (
    POINT_COLUMNS,
    get_fits,
    get_history,
    get_points,
    get_snapshot_fits,
    get_snapshot_points,
    get_snapshot_rejection_counts,
    get_timeline,
    stream_points,
)
from src.db.models.operations import OptionPricingConvention
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal
from src.routes.admin_tasks import _require_admin
from src.services.operation_runs import enqueue_task, get_run, list_runs, run_to_dict
from src.tasks import run_iv_surface

router = APIRouter(tags=["iv-surface"])
TEHRAN = ZoneInfo("Asia/Tehran")


def _validate_inputs(config: IVSurfaceRunConfig) -> OptionPricingConvention:
    with SessionLocal() as session:
        stock = session.get(StockInstrument, config.underlying_instrument_code)
        convention = session.get(OptionPricingConvention, config.pricing_convention_id)
    errors = []
    if stock is None:
        errors.append({"field": "underlying_instrument_code", "message": "unknown stock instrument"})
    if convention is None:
        errors.append({"field": "pricing_convention_id", "message": "unknown pricing convention"})
    elif not convention.approved or convention.approved_at is None:
        errors.append({"field": "pricing_convention_id", "message": "pricing convention is not approved"})
    elif not convention.black76_compatible:
        errors.append({"field": "pricing_convention_id", "message": "pricing convention is not Black-76 compatible"})
    elif config.start_date < convention.effective_from or (convention.effective_to and config.end_date > convention.effective_to):
        errors.append({"field": "pricing_convention_id", "message": "convention is not effective for the full run"})
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    return convention


@router.post("/admin/tasks/run-iv-surface")
async def create_iv_surface_run(request: Request, config: IVSurfaceRunConfig):
    await _require_admin(request)
    convention = _validate_inputs(config)
    now = datetime.now(TEHRAN)
    run_id = str(uuid.uuid4())
    days = (config.end_date - config.start_date).days + 1
    per_day = len(aligned_snapshots(config.start_date, config.session_start, config.session_end, config.interval_seconds))
    convention_version = (convention.updated_at or convention.approved_at).isoformat()
    row: dict[str, Any] = {
        "run_id": run_id, "underlying_instrument_code": config.underlying_instrument_code,
        "start_date": config.start_date, "end_date": config.end_date,
        "session_start": config.session_start.isoformat(), "session_end": config.session_end.isoformat(),
        "interval_seconds": config.interval_seconds, "max_quote_age_seconds": config.max_quote_age_seconds,
        "forward_source": "executable_parity_interval", "rate_source": "bond_curve_then_manual",
        "pricing_convention_id": str(config.pricing_convention_id),
        "pricing_convention_version": convention_version, "model_version": MODEL_VERSION,
        "config_json": config.model_dump_json(), "status": "queued", "target_snapshot_count": per_day * days,
        "completed_snapshot_count": 0, "point_count": 0, "fit_count": 0, "warning_count": 0,
        "quality_summary": "{}", "error": "", "created_at": now, "updated_at": now,
    }
    operation, task = enqueue_task(
        run_iv_surface,
        args=[run_id],
        family="iv_orc",
        run_type="iv_orc.surface",
        target=config.underlying_instrument_code,
        config=row,
        start_date=config.start_date,
        end_date=config.end_date,
        progress_total=per_day * days,
        run_id=run_id,
        created_by=request.session.get("user") or "admin",
    )
    return {"run_id": str(operation.run_id), "task_id": task.id, "status": "queued", "interval_seconds": config.interval_seconds}


@router.get("/api/v1/iv-surface/runs")
async def iv_runs(request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    await _require_admin(request)
    _, rows = list_runs(family="iv_orc", limit=limit, offset=offset)
    return {"items": [run_to_dict(row) for row in rows], "limit": limit, "offset": offset}


async def _checked_run(request: Request, run_id: uuid.UUID) -> dict[str, Any]:
    await _require_admin(request)
    row = get_run(str(run_id))
    if row is None:
        raise HTTPException(status_code=404, detail="IV surface run not found")
    return run_to_dict(row)


@router.get("/api/v1/iv-surface/runs/{run_id}")
async def iv_run(request: Request, run_id: uuid.UUID):
    return await _checked_run(request, run_id)


@router.get("/api/v1/iv-surface/runs/{run_id}/points")
async def iv_points(request: Request, run_id: uuid.UUID, limit: int = Query(50000, ge=1, le=200000)):
    await _checked_run(request, run_id)
    return {"items": await get_points(str(run_id), limit)}


@router.get("/api/v1/iv-surface/runs/{run_id}/fits")
async def iv_fits(request: Request, run_id: uuid.UUID, limit: int = Query(50000, ge=1, le=200000)):
    await _checked_run(request, run_id)
    return {"items": await get_fits(str(run_id), limit)}


@router.get("/api/v1/iv-surface/runs/{run_id}/timeline")
async def iv_timeline(request: Request, run_id: uuid.UUID):
    await _checked_run(request, run_id)
    snapshots, expiries = await get_timeline(str(run_id))
    return {"snapshots": snapshots, "expiries": expiries}


@router.get("/api/v1/iv-surface/runs/{run_id}/snapshot")
async def iv_snapshot(
    request: Request,
    run_id: uuid.UUID,
    snapshot_time: datetime,
    steps: int = Query(41, ge=11, le=201),
):
    await _checked_run(request, run_id)
    rejection_counts = await get_snapshot_rejection_counts(str(run_id), snapshot_time)
    if not rejection_counts:
        raise HTTPException(status_code=404, detail="IV snapshot not found for this run")
    points = await get_snapshot_points(str(run_id), snapshot_time)
    fits = await get_snapshot_fits(str(run_id), snapshot_time)
    grid = []
    for fit in fits:
        if not fit["converged"]:
            continue
        params = WingParameters(**{name: float(fit[name]) for name in ("vc", "sc", "pc", "cc", "dc", "uc")})
        for index in range(steps):
            x = -1.0 + 2.0 * index / (steps - 1)
            grid.append({
                "snapshot_time": fit["snapshot_time"], "expiry_date": fit["expiry_date"], "side": fit["side"],
                "log_moneyness": x, "dte": float(fit["ttm_years"]) * 365.25, "iv": orc_wing(x, params),
                "quality_flags": fit["quality_flags"],
            })
    valid_point_count = rejection_counts.pop("", 0)
    return {
        "snapshot_time": snapshot_time,
        "points": points,
        "fits": fits,
        "grid": grid,
        "valid_point_count": valid_point_count,
        "rejection_counts": rejection_counts,
    }


@router.get("/api/v1/iv-surface/runs/{run_id}/history")
async def iv_history(request: Request, run_id: uuid.UUID, expiry_date: date, side: str = Query(..., pattern="^(bid|ask)$")):
    await _checked_run(request, run_id)
    fits, forwards = await get_history(str(run_id), expiry_date, side)
    return {"fits": fits, "forwards": forwards}


@router.get("/api/v1/iv-surface/runs/{run_id}/grid")
async def iv_grid(request: Request, run_id: uuid.UUID, steps: int = Query(41, ge=11, le=201)):
    await _checked_run(request, run_id)
    fits = await get_fits(str(run_id), 200000)
    items = []
    for fit in fits:
        if not fit["converged"]:
            continue
        params = WingParameters(**{name: float(fit[name]) for name in ("vc", "sc", "pc", "cc", "dc", "uc")})
        for index in range(steps):
            x = -1.0 + 2.0 * index / (steps - 1)
            items.append({
                "snapshot_time": fit["snapshot_time"], "expiry_date": fit["expiry_date"], "side": fit["side"],
                "log_moneyness": x, "dte": float(fit["ttm_years"]) * 365.25, "iv": orc_wing(x, params),
                "quality_flags": fit["quality_flags"],
            })
    return {"items": items}


def _csv_stream(run_id: str, run: dict[str, Any]):
    config = json.loads(run["config_json"])
    extras = (
        run["interval_seconds"],
        json.dumps(config, sort_keys=True),
        run["pricing_convention_version"],
        run["model_version"],
    )
    fields = [
        *POINT_COLUMNS,
        "run_interval_seconds",
        "run_config_json",
        "pricing_convention_version",
        "model_version",
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(fields)
    yield buffer.getvalue()
    for block in stream_points(run_id):
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerows([(*row, *extras) for row in block])
        yield buffer.getvalue()


@router.get("/api/v1/iv-surface/runs/{run_id}/export.csv")
async def iv_export(request: Request, run_id: uuid.UUID):
    run = await _checked_run(request, run_id)
    interval = run["interval_seconds"]
    return StreamingResponse(
        _csv_stream(str(run_id), run),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="iv-surface-{run_id}-{interval}s.csv"'},
    )
