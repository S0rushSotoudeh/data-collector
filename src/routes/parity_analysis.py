from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from starlette.requests import Request

from src.analytics.parity import CALCULATION_VERSION
from src.analytics.parity_config import ParityRunConfig
from src.analytics.parity_engine import aligned_snapshots
from src.db.clickhouse.parity import get_snapshots
from src.db.models.option import OptionInstrument
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal
from src.routes.admin_tasks import _require_admin
from src.services.operation_runs import enqueue_task, get_run, list_runs, run_to_dict
from src.tasks import run_parity_analysis

router = APIRouter(tags=["parity-analysis"])
TEHRAN = ZoneInfo("Asia/Tehran")


def _validate_package(config: ParityRunConfig) -> tuple[float, date]:
    errors: list[dict[str, str]] = []
    with SessionLocal() as session:
        stock = session.get(StockInstrument, config.underlying_instrument_code)
        call = session.get(OptionInstrument, config.call_instrument_code)
        put = session.get(OptionInstrument, config.put_instrument_code)
    if stock is None: errors.append({"field": "underlying_instrument_code", "message": "unknown stock instrument"})
    if call is None: errors.append({"field": "call_instrument_code", "message": "unknown call instrument"})
    if put is None: errors.append({"field": "put_instrument_code", "message": "unknown put instrument"})
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    call_type = (call.option_type or "").lower()
    put_type = (put.option_type or "").lower()
    if call_type not in {"call", "c"}: errors.append({"field": "call_instrument_code", "message": "selected instrument is not a call"})
    if put_type not in {"put", "p"}: errors.append({"field": "put_instrument_code", "message": "selected instrument is not a put"})
    if call.strike_price is None or put.strike_price is None or call.strike_price != put.strike_price:
        errors.append({"field": "package", "message": "call and put strikes must match"})
    if call.expiry_date is None or put.expiry_date is None or call.expiry_date != put.expiry_date:
        errors.append({"field": "package", "message": "call and put expiries must match"})
    call_underlying = call.underlying_instrument_code or ""
    put_underlying = put.underlying_instrument_code or ""
    if call_underlying != put_underlying or call_underlying != config.underlying_instrument_code:
        errors.append({"field": "package", "message": "call, put, and selected underlying must match"})
    if call.expiry_date and config.start_date > call.expiry_date:
        errors.append({"field": "start_date", "message": "analysis starts after option expiry"})
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    return float(call.strike_price), call.expiry_date


@router.post("/admin/tasks/run-parity-analysis")
async def create_parity_run(request: Request, config: ParityRunConfig):
    await _require_admin(request)
    strike, expiry = _validate_package(config)
    now = datetime.now(TEHRAN)
    run_id = str(uuid.uuid4())
    fees = config.effective_fees()
    config_payload = config.model_dump(mode="json") | {"strike": strike, "expiry_date": expiry.isoformat()}
    row: dict[str, Any] = {
        "run_id": run_id,
        "strike": strike, "expiry_date": expiry,
        **{name: getattr(config, name) for name in (
            "underlying_instrument_code", "call_instrument_code", "put_instrument_code",
            "start_date", "end_date", "interval_seconds", "max_quote_age_seconds",
            "minimum_ytm_spread_bps", "funding_source", "manual_borrowing_rate",
            "borrowing_spread", "stock_fee_category", "option_fee_category", "multiplier", "tick_size",
        )},
        "start_time": config.start_time.isoformat(), "end_time": config.end_time.isoformat(),
        "expiry_cutoff": config.expiry_cutoff.isoformat(),
        # Kept only because parity-v2 history shares this table schema.
        "margin_value": 0.0, "margin_unit": "legacy_unused", "margin_per_share": 0.0,
        **{f"{name}_fee": value for name, value in fees.__dict__.items()},
        "calculation_version": CALCULATION_VERSION,
        "config_json": json.dumps(config_payload), "status": "queued", "snapshot_count": 0,
        "valid_count": 0, "warning_count": 0, "invalid_count": 0, "opportunity_count": 0,
        "error": "", "created_at": now, "updated_at": now,
    }
    total = 0
    day = config.start_date
    while day <= config.end_date:
        total += len(aligned_snapshots(day, config.start_time, config.end_time, config.interval_seconds))
        day += timedelta(days=1)
    operation, task = enqueue_task(
        run_parity_analysis,
        args=[run_id],
        family="parity",
        run_type="parity.analysis",
        target=config.underlying_instrument_code,
        config=row,
        start_date=config.start_date,
        end_date=config.end_date,
        progress_total=total,
        run_id=run_id,
        created_by=request.session.get("user") or "admin",
    )
    return {"run_id": str(operation.run_id), "task_id": task.id, "status": "queued"}


@router.get("/api/v1/parity-analysis/runs")
async def parity_runs(request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    await _require_admin(request)
    _, rows = list_runs(family="parity", limit=limit, offset=offset)
    return {"items": [run_to_dict(row) for row in rows], "limit": limit, "offset": offset}


@router.get("/api/v1/parity-analysis/runs/{run_id}")
async def parity_run(request: Request, run_id: uuid.UUID):
    await _require_admin(request)
    row = get_run(str(run_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Parity analysis run not found")
    return run_to_dict(row)


@router.get("/api/v1/parity-analysis/runs/{run_id}/snapshots")
async def parity_snapshots(
    request: Request, run_id: uuid.UUID, trade_date: date | None = None,
    start_time: time | None = None, end_time: time | None = None,
    limit: int = Query(10000, ge=1, le=50000),
):
    await _require_admin(request)
    if get_run(str(run_id)) is None:
        raise HTTPException(status_code=404, detail="Parity analysis run not found")
    return {"items": await get_snapshots(str(run_id), trade_date, start_time, end_time, limit)}
