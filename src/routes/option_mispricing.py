from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import StreamingResponse

from src.analytics.mispricing_config import OptionMispricingRunConfig
from src.analytics.mispricing_engine import CONFIGURATION_VERSION, MODEL_VERSION
from src.analytics.mispricing_universe import discover_option_universe
from src.analytics.parity_engine import aligned_snapshots
from src.db.clickhouse.mispricing import (
    count_observations, get_fits, get_observations, get_rankings, get_snapshot_summaries,
    insert_universe,
)
from src.db.models.operations import OptionPricingConvention
from src.db.models.option import OptionInstrument
from src.db.session import SessionLocal
from src.routes.admin_tasks import _require_admin
from src.services.operation_runs import enqueue_task, get_run, list_runs, run_to_dict
from src.tasks import run_option_mispricing

router = APIRouter(tags=["option-mispricing"])
TEHRAN = ZoneInfo("Asia/Tehran")


def _underlying_symbols(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Decorate persisted numeric underlying keys with their human symbol."""
    codes = {str(row.get("underlying_instrument_code")) for row in rows if row.get("underlying_instrument_code")}
    if not codes:
        return rows
    with SessionLocal() as session:
        mapping = dict(session.execute(
            select(OptionInstrument.underlying_instrument_code, OptionInstrument.underlying_symbol)
            .where(OptionInstrument.underlying_instrument_code.in_(codes))
            .where(OptionInstrument.underlying_symbol.is_not(None))
        ).all())
    for row in rows:
        code = row.get("underlying_instrument_code")
        row["underlying_symbol"] = mapping.get(str(code)) if code else None
    return rows


def _pricing_convention(config: OptionMispricingRunConfig) -> OptionPricingConvention:
    with SessionLocal() as session:
        convention = session.get(OptionPricingConvention, config.pricing_convention_id)
    errors = []
    if convention is None:
        errors.append({"field": "pricing_convention_id", "message": "unknown pricing convention"})
    elif not convention.approved or convention.approved_at is None:
        errors.append({"field": "pricing_convention_id", "message": "pricing convention is not approved"})
    elif not convention.black76_compatible or convention.exercise_style.lower() not in {"european", "european-style"}:
        errors.append({"field": "pricing_convention_id", "message": "pricing convention is not Black-76 compatible"})
    elif config.trade_date < convention.effective_from or (convention.effective_to and config.trade_date > convention.effective_to):
        errors.append({"field": "pricing_convention_id", "message": "pricing convention is not effective on the trade date"})
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    return convention


@router.get("/api/v1/option-mispricing/universe-preview")
async def universe_preview(
    request: Request, trade_date: date, start_time: time = time(8, 30),
    end_time: time = time(12, 30), expiry_cutoff: time = time(12, 30),
):
    await _require_admin(request)
    if start_time > end_time:
        raise HTTPException(status_code=422, detail="start_time must not be after end_time")
    return await discover_option_universe(trade_date, start_time, end_time, expiry_cutoff)


@router.post("/api/v1/option-mispricing/runs")
@router.post("/admin/tasks/run-option-mispricing")
async def create_mispricing_run(request: Request, config: OptionMispricingRunConfig):
    await _require_admin(request)
    convention = _pricing_convention(config)
    preview = await discover_option_universe(config.trade_date, config.start_time, config.end_time, config.expiry_cutoff)
    if not preview["contract_count"]:
        raise HTTPException(status_code=422, detail={"errors": [{"field": "trade_date", "message": "no historical option quotes in the selected session"}]})
    underlyings = {row["underlying_instrument_code"] for row in preview["contracts"] if row["underlying_instrument_code"]}
    if not underlyings:
        raise HTTPException(status_code=422, detail={"errors": [{"field": "trade_date", "message": "quoted contracts have no underlying mappings"}]})
    run_id = str(uuid.uuid4())
    now = datetime.now(TEHRAN)
    convention_version = (convention.updated_at or convention.approved_at).isoformat()
    universe_payload = json.dumps([
        {key: str(value) if isinstance(value, (date, datetime)) else value for key, value in row.items()}
        for row in preview["contracts"]
    ], sort_keys=True, ensure_ascii=False)
    universe_hash = hashlib.sha256(universe_payload.encode()).hexdigest()
    for row in preview["contracts"]:
        row.update({
            "run_id": run_id, "trade_date": config.trade_date, "model_version": MODEL_VERSION,
            "configuration_version": CONFIGURATION_VERSION,
            "pricing_convention_id": str(convention.convention_id),
            "pricing_convention_version": convention_version, "frozen_at": now,
        })
    insert_universe(preview["contracts"])
    total = len(aligned_snapshots(config.trade_date, config.start_time, config.end_time, config.interval_seconds)) * len(underlyings)
    metadata: dict[str, Any] = {
        "run_config": config.model_dump(mode="json"), "model_version": MODEL_VERSION,
        "configuration_version": CONFIGURATION_VERSION, "pricing_convention_id": str(convention.convention_id),
        "pricing_convention_version": convention_version,
        "pricing_convention_name": convention.name, "price_factor": 10.0 if convention.price_unit.lower() in {"toman", "tomans"} else 1.0,
        "universe_hash": universe_hash, "frozen_contract_count": preview["contract_count"],
        "frozen_underlying_count": len(underlyings), "eligible_group_count": preview["eligible_group_count"],
        "trade_date": config.trade_date.isoformat(), "interval_seconds": config.interval_seconds,
        "start_time": config.start_time.isoformat(), "end_time": config.end_time.isoformat(),
        "max_quote_age_seconds": config.max_quote_age_seconds,
    }
    operation, task = enqueue_task(
        run_option_mispricing, args=[run_id], family="option_mispricing",
        run_type="option_mispricing.market_scan", target="market_wide", config=metadata,
        start_date=config.trade_date, end_date=config.trade_date, progress_total=total,
        run_id=run_id, created_by=request.session.get("user") or "admin",
    )
    return {"run_id": str(operation.run_id), "task_id": task.id, "status": "queued", "universe": {
        "contract_count": preview["contract_count"], "underlying_count": len(underlyings),
        "eligible_group_count": preview["eligible_group_count"], "hash": universe_hash,
    }}


async def _checked_run(request: Request, run_id: uuid.UUID) -> dict[str, Any]:
    await _require_admin(request)
    row = get_run(str(run_id))
    if row is None or row.family != "option_mispricing":
        raise HTTPException(status_code=404, detail="Option mispricing run not found")
    return run_to_dict(row)


@router.get("/api/v1/option-mispricing/runs")
async def mispricing_runs(request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    await _require_admin(request)
    total, rows = list_runs(family="option_mispricing", limit=limit, offset=offset)
    return {"items": [run_to_dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/api/v1/option-mispricing/runs/{run_id}")
async def mispricing_run(request: Request, run_id: uuid.UUID):
    return await _checked_run(request, run_id)


@router.get("/api/v1/option-mispricing/runs/{run_id}/rankings")
async def rankings(request: Request, run_id: uuid.UUID, sort_by: str = Query("p90", pattern="^(p90|median|largest|affected_contracts)$")):
    await _checked_run(request, run_id)
    return {"items": _underlying_symbols(await get_rankings(str(run_id), sort_by))}


@router.get("/api/v1/option-mispricing/runs/{run_id}/underlyings/{underlying}/snapshots")
async def snapshot_summaries(request: Request, run_id: uuid.UUID, underlying: str, expiry_date: date | None = None):
    await _checked_run(request, run_id)
    return {"items": _underlying_symbols(await get_snapshot_summaries(str(run_id), underlying, expiry_date))}


@router.get("/api/v1/option-mispricing/runs/{run_id}/observations")
async def observations(
    request: Request, run_id: uuid.UUID, underlying: str | None = None, expiry_date: date | None = None,
    option_type: str | None = Query(None, pattern="^(call|put)$"), snapshot_time: datetime | None = None,
    quality_status: str | None = Query(None, pattern="^(eligible|valid|warning|invalid)$"),
    minimum_absolute_distance_bps: float | None = Query(None, ge=0),
    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=5000),
):
    await _checked_run(request, run_id)
    filters = dict(
        run_id=str(run_id), underlying_instrument_code=underlying, expiry_date=expiry_date,
        option_type=option_type, snapshot_time=snapshot_time, quality_status=quality_status,
        minimum_absolute_distance_bps=minimum_absolute_distance_bps,
    )
    return {"items": _underlying_symbols(await get_observations(**filters, offset=offset, limit=limit)),
            "total": await count_observations(**filters), "offset": offset, "limit": limit}


@router.get("/api/v1/option-mispricing/runs/{run_id}/fits")
async def fits(
    request: Request, run_id: uuid.UUID, underlying: str | None = None, expiry_date: date | None = None,
    snapshot_time: datetime | None = None, quality_status: str | None = Query(None, pattern="^(eligible|valid|warning|invalid)$"),
    limit: int = Query(10000, ge=1, le=100000),
):
    await _checked_run(request, run_id)
    return {"items": _underlying_symbols(await get_fits(str(run_id), underlying, expiry_date, snapshot_time, quality_status, limit))}


@router.get("/api/v1/option-mispricing/runs/{run_id}/export.csv")
async def export_csv(
    request: Request, run_id: uuid.UUID, underlying: str | None = None, expiry_date: date | None = None,
    option_type: str | None = None, quality_status: str | None = Query("eligible", pattern="^(eligible|valid|warning|invalid)$"),
    minimum_absolute_distance_bps: float | None = Query(None, ge=0),
):
    run = await _checked_run(request, run_id)
    rows = await get_observations(
        run_id=str(run_id), underlying_instrument_code=underlying, expiry_date=expiry_date,
        option_type=option_type, quality_status=quality_status,
        minimum_absolute_distance_bps=minimum_absolute_distance_bps, limit=1_000_000,
    )
    buffer = io.StringIO()
    rows = _underlying_symbols(rows)
    fields = list(rows[0]) if rows else ["run_id", "underlying_symbol", "instrument_code", "fair_price"]
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader(); writer.writerows(rows)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="option-mispricing-{run["trade_date"]}-{run_id}.csv"'
    })
