from __future__ import annotations

import json
import uuid
import math
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import AwareDatetime, ValidationError
from sqlalchemy import select
import numpy as np
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import StreamingResponse

from src.analytics.gold_consensus import reconstruct, filter_grid
from src.analytics.gold_consensus_config import DatasetManifest, GoldKalmanRunConfig, engine_identity
from src.analytics.gold_consensus_engine import progress_total, validate_inputs, validation_usable
from src.db.clickhouse.gold_consensus import (import_dataset, list_datasets, query_rows, stream_csv,
    dataset_row, display_mapping, manifest_fingerprint, load_events, get_client)
from src.db.models.gold_consensus import GoldKalmanCalibration
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal
from src.routes.admin_tasks import _require_admin
from src.services.operation_runs import enqueue_task, get_run, list_runs, run_to_dict
from src.tasks import run_gold_kalman
from src.celery_app import celery

router = APIRouter(tags=["gold-kalman"])
Method = Literal["scheduled", "frozen", "peer_median"]


async def checked(request, run_id):
    await _require_admin(request)
    run = await run_in_threadpool(get_run, str(run_id))
    if run is None or run.family != "gold_kalman":
        raise HTTPException(404, "Gold Kalman run not found")
    return run


@router.get("/api/v1/gold-kalman/datasets")
async def datasets(request: Request):
    await _require_admin(request)
    def read():
        items = list_datasets()
        for item in items:
            m = item["manifest"]
            codes = sorted({s for session in m["sessions"] for s in session["eligible_symbols"]})
            item["display_symbols"] = display_mapping(codes, m["clock"], m.get("display_symbols"))
        return items
    return {"items": await run_in_threadpool(read)}


@router.get("/api/v1/gold-kalman/readiness")
async def readiness(request: Request):
    await _require_admin(request)
    def read():
        with SessionLocal() as db:
            rows = db.execute(select(StockInstrument).where(StockInstrument.is_gold_etf.is_(True))).scalars().all()
        return {"ready": False, "source": "stock_order_book", "clock": "exchange_time_only_unverified",
            "items": [{"value": r.instrument_code, "symbol": r.symbol or "Symbol unavailable", "name": r.name_fa} for r in rows],
            "blockers": ["Historical trading calendar and session boundaries are not verified.",
                         "Historical ETF membership is not established by current instrument flags.",
                         "Historical trading phases are absent; unknown phase must suppress scoring.",
                         "Second-resolution replacement rows do not preserve original intrasecond ordering.",
                         "Storage ingestion timestamps are not proven historical availability; latency-realistic replay is unavailable."],
            "next_step": "Supply a versioned calendar, historical membership, phase history and a defensible source-clock/order convention through data management before creating a real snapshot. No demo data are substituted."}
    return await run_in_threadpool(read)


@router.post("/api/v1/gold-kalman/preflight")
async def preflight(request: Request, config: GoldKalmanRunConfig):
    await _require_admin(request)
    try:
        await run_in_threadpool(validate_inputs, config)
    except ValueError as exc:
        return {"ready": False, "errors": [str(exc)], "warnings": []}
    return {"ready": True, "errors": [], "warnings": [
        "Calendar and observation upper bounds pass. Peer overlap, distinct grid changes, calibration residual scale and actual initialization may still suppress scores. This is not quantitative validation."]}


def result_context(run):
    policy = run.config["policy"]
    dataset = dataset_row(policy["dataset_id"])
    manifest = run.config.get("dataset_manifest") or (dataset.manifest if dataset else {})
    labels = display_mapping(policy["symbols"], manifest.get("clock"), run.config.get("display_symbols") or manifest.get("display_symbols"))
    return {"dataset_name": run.config.get("dataset_name") or (dataset.name if dataset else "Unavailable dataset"),
            "manifest": manifest, "display_symbols": labels,
            "legacy_provenance": not bool(run.config.get("engine_identity")),
            "metadata_warning": ("Legacy run: display metadata was not frozen at submission. " if not run.config.get("display_symbols") else "")
                + ("Metadata quality warning: one or more ETF symbols are unavailable." if "Symbol unavailable" in labels.values() else ""),
            "analytical_usable": validation_usable(run.result)}


@router.post("/api/v1/gold-kalman/datasets")
async def upload_dataset(request: Request, manifest: str = Form(...), events: UploadFile = File(...)):
    await _require_admin(request)
    try:
        parsed = DatasetManifest.model_validate_json(manifest)
        return await run_in_threadpool(import_dataset, parsed, events.file)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/admin/tasks/run-gold-kalman")
async def submit(request: Request, config: GoldKalmanRunConfig):
    await _require_admin(request)
    try:
        dataset, manifest = await run_in_threadpool(validate_inputs, config)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    run_id = str(uuid.uuid4())
    labels = await run_in_threadpool(display_mapping, config.symbols, manifest.clock, manifest.display_symbols)
    start, end = config.evaluation_bounds()
    operation, task = await run_in_threadpool(enqueue_task, celery.tasks["src.tasks.run_gold_kalman"],
        args=[run_id], run_id=run_id, config={"policy": config.model_dump(mode="json"),
        "policy_hash": config.policy_hash(), "dataset_sha256": dataset.sha256,
        "dataset_name": manifest.name, "dataset_manifest": manifest.model_dump(mode="json"),
        "manifest_sha256": manifest_fingerprint(dataset.manifest), "display_symbols": labels,
        "engine_identity": engine_identity()},
        target=f"{len(config.symbols)} Gold ETFs | {config.mode} {start.date()}–{end.date()}",
        start_date=start.date(), end_date=end.date(), progress_total=progress_total(config, manifest),
        created_by=request.session.get("user") or "admin")
    return {"run_id": str(operation.run_id), "task_id": task.id, "status": "queued"}


@router.get("/api/v1/gold-kalman/runs")
async def runs(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    await _require_admin(request)
    total, rows = await run_in_threadpool(list_runs, family="gold_kalman", limit=limit, offset=offset)
    return {"total": total, "items": [run_to_dict(row) for row in rows]}


@router.get("/api/v1/gold-kalman/runs/{run_id}")
async def detail(request: Request, run_id: uuid.UUID):
    run = await checked(request, run_id)
    return run_to_dict(run) | {"context": await run_in_threadpool(result_context, run)}


@router.get("/api/v1/gold-kalman/runs/{run_id}/calibrations")
async def calibrations(request: Request, run_id: uuid.UUID):
    await checked(request, run_id)
    def read():
        with SessionLocal() as db:
            rows = db.execute(select(GoldKalmanCalibration).where(GoldKalmanCalibration.run_id == run_id)
                .order_by(GoldKalmanCalibration.session_open, GoldKalmanCalibration.method)).scalars().all()
            return [{"calibration_id": str(r.calibration_id), "method": r.method, "session_open": r.session_open, **r.payload} for r in rows]
    return {"items": await run_in_threadpool(read)}


@router.get("/api/v1/gold-kalman/runs/{run_id}/evaluation")
async def evaluation(request: Request, run_id: uuid.UUID):
    run = await checked(request, run_id)
    return {"status": run.status, "partial": run.status != "completed", "result": run.result}


@router.get("/api/v1/gold-kalman/runs/{run_id}/timeline")
async def timeline(request: Request, run_id: uuid.UUID, method: Method = "scheduled",
                   limit: int = Query(2000, ge=1, le=10000), offset: int = Query(0, ge=0),
                   start: AwareDatetime | None = None, end: AwareDatetime | None = None):
    await checked(request, run_id)
    rows = await run_in_threadpool(query_rows, "market", run_id, method=method, limit=limit + 1, offset=offset, compact=True, start=start, end=end)
    return {"items": rows[:limit], "next_offset": offset + limit if len(rows) > limit else None}


@router.get("/api/v1/gold-kalman/runs/{run_id}/snapshot")
async def snapshot(request: Request, run_id: uuid.UUID, decision_time: AwareDatetime, method: Method = "scheduled"):
    run = await checked(request, run_id)
    rows = await run_in_threadpool(query_rows, "scores", run_id, method=method, decision_time=decision_time, limit=100)
    rows.sort(key=lambda row: row["z_score"])
    context = await run_in_threadpool(result_context, run)
    for row in rows:
        row["symbol"] = context["display_symbols"].get(row["instrument_code"], "Symbol unavailable")
    return {"items": rows}


@router.get("/api/v1/gold-kalman/runs/{run_id}/history")
async def history(request: Request, run_id: uuid.UUID, symbol: str, method: Method = "scheduled",
                  limit: int = Query(2000, ge=1, le=10000), offset: int = Query(0, ge=0),
                  start: AwareDatetime | None = None, end: AwareDatetime | None = None):
    await checked(request, run_id)
    rows = await run_in_threadpool(query_rows, "scores", run_id, method=method, symbol=symbol, limit=limit + 1, offset=offset, start=start, end=end)
    return {"items": rows[:limit], "next_offset": offset + limit if len(rows) > limit else None}


@router.get("/api/v1/gold-kalman/runs/{run_id}/export.csv")
async def export(request: Request, run_id: uuid.UUID, kind: Literal["scores", "market", "outcomes"] = "scores", method: Method = "scheduled"):
    run = await checked(request, run_id)
    context = await run_in_threadpool(result_context, run)
    def content():
        policy = run.config["policy"] | {"symbols": list(context["display_symbols"].values())}
        yield "# " + json.dumps({"run_id": str(run_id), "status": run.status, "method": method,
            "policy": policy, "dataset_sha256": run.config.get("dataset_sha256"),
            "engine_identity": run.config.get("engine_identity", "unrecorded legacy version"),
            "clock": context["manifest"].get("clock"), "metadata_warning": context["metadata_warning"]}, ensure_ascii=False) + "\n"
        yield from stream_csv(kind, run_id, method, context["display_symbols"])
    return StreamingResponse(content(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="gold-{run_id}-{kind}.csv"'})


@router.get("/api/v1/gold-kalman/runs/{run_id}/explain")
async def explain(request: Request, run_id: uuid.UUID, decision_time: AwareDatetime,
                  symbol: str, method: Method = "scheduled"):
    run = await checked(request, run_id)
    if symbol not in run.config["policy"]["symbols"]:
        raise HTTPException(422, "ETF is not in this saved run")
    def read():
        context = result_context(run)
        cfg = GoldKalmanRunConfig.model_validate(run.config["policy"])
        manifest = DatasetManifest.model_validate(context["manifest"])
        when = decision_time.timestamp()
        start, end = (v.timestamp() for v in cfg.evaluation_bounds())
        index = next((i for i, s in enumerate(manifest.sessions) if s.open.timestamp() <= when < s.close.timestamp()), None)
        response = {"run_id": str(run_id), "method": method, "decision_time": decision_time,
                    "symbol": context["display_symbols"][symbol], "engine_identity": run.config.get("engine_identity"),
                    "model_version": cfg.model_version}
        if index is None or not start <= when < end or when != math.ceil(when):
            return response | {"reason": "No decision at this instant inside the saved evaluation sessions."}
        session = manifest.sessions[index]
        start, end = max(start, session.open.timestamp()), min(end, session.close.timestamp())
        events = load_events(cfg.dataset_id, index)
        # Two grid points preserve the new/cached distinction without replaying for diagnostics.
        times = np.arange(max(math.ceil(start), when - 1), when + 1)
        grid = reconstruct(events, cfg.symbols, times, start, end, cfg.max_quote_age, set(session.eligible_symbols))
        j = cfg.symbols.index(symbol)
        raw = events.get(symbol, np.empty((0, 8)))
        raw = raw[(raw[:, 0] >= start) & (raw[:, 0] <= when)]
        source = raw[-1] if len(raw) else None
        finite = lambda value: float(value) if np.isfinite(value) else None
        response["inputs"] = dict(zip(("bid", "ask", "bid_qty", "ask_qty"), map(finite, grid.books[-1, j])))
        response["inputs"].update({"quote_time": finite(grid.quote_times[-1, j]),
            "available_at": float(source[0]) if source is not None else None,
            "sequence": int(source[2]) if source is not None else None,
            "quote_age": finite(when - grid.quote_times[-1, j]),
            "delivery_delay": float(source[0] - source[1]) if source is not None else None,
            "phase": ("unknown", "continuous", "auction", "halted")[grid.phases[-1, j]],
            "new_measurement": bool(grid.new[-1, j]), "eligible": symbol in session.eligible_symbols,
            "valid": bool(grid.valid[-1, j]), "midpoint": finite(grid.mid[-1, j]), "microprice": finite(grid.micro[-1, j])})
        response["inputs"]["suppression_reason"] = (
            "historically_ineligible" if symbol not in session.eligible_symbols else
            "no_available_source_event" if source is None else
            "non_continuous_phase" if source[7] != 1 else
            "stale_quote" if when - source[1] > cfg.max_quote_age else
            "invalid_book" if not grid.valid[-1, j] else "")
        stored = query_rows("scores", run_id, method=method, decision_time=decision_time, symbol=symbol, limit=1)
        response["stored"] = stored[0] if stored else None
        if response["stored"]:
            response["stored"] = {k: v for k, v in response["stored"].items() if k != "instrument_code"}
        if run.config.get("engine_identity") != engine_identity():
            return response | {"reason": "Full trace unavailable: this legacy run has no matching recorded engine identity. Stored outputs are unchanged; current-engine diagnostics are shown separately."}
        dataset = dataset_row(cfg.dataset_id)
        if dataset.sha256 != run.config["dataset_sha256"] or manifest_fingerprint(dataset.manifest) != run.config.get("manifest_sha256"):
            return response | {"reason": "Trace unavailable: immutable dataset identity no longer matches."}
        with SessionLocal() as db:
            fit = db.execute(select(GoldKalmanCalibration).where(GoldKalmanCalibration.run_id == run_id,
                GoldKalmanCalibration.method == method, GoldKalmanCalibration.session_open == session.open)).scalar_one_or_none()
        if fit is None:
            return response | {"reason": "Calibration is not committed yet."}
        grid = reconstruct(events, cfg.symbols, np.arange(math.ceil(start), when + 1), start, end,
                           cfg.max_quote_age, set(session.eligible_symbols))
        output = filter_grid(grid, cfg.symbols, fit.payload, cfg, method, trace_at=len(grid.times)-1)
        trace = output["trace"]
        value = trace.pop("values", {}).get(symbol)
        trace["update_symbols"] = [context["display_symbols"].get(s, "Symbol unavailable") for s in trace.get("update_symbols", [])]
        response.update({"calibration_id": str(fit.calibration_id), "trace": trace, "value": value,
            "calibration": {key: fit.payload.get(key) for key in
                ("cutoff", "effective_time", "selected_sessions", "missing_sessions", "r_ref", "delta_ref", "q")},
            "alert_conditions": {"minimum_absolute_z": cfg.z_alert, "consecutive_magnitude_intervals": cfg.k,
                                 "direction_changes_reset": False},
            "reason": response["inputs"]["suppression_reason"] or trace.get("reason") or (fit.payload.get("exclusions", {}).get(symbol, "Excluded from calibration.") if value is None else ""),
            "formula": "median of other fresh normalized log microprices; Kalman modeled variance for standardization" if method == "peer_median" else "current-batch excluded Kalman prediction before full update",
            "matches_stored": bool(value and stored and all(math.isclose(value[k], stored[0][k], rel_tol=1e-9, abs_tol=1e-10) for k in ("fair_price", "z_score", "residual", "persistence")))})
        return response
    return await run_in_threadpool(read)
