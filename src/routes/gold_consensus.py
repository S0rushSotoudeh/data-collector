from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import AwareDatetime, ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import StreamingResponse

from src.analytics.gold_consensus_config import DatasetManifest, GoldKalmanRunConfig
from src.analytics.gold_consensus_engine import progress_total, validate_inputs
from src.db.clickhouse.gold_consensus import import_dataset, list_datasets, query_rows, stream_csv
from src.db.models.gold_consensus import GoldKalmanCalibration
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
    return {"items": await run_in_threadpool(list_datasets)}


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
    start, end = config.evaluation_bounds()
    operation, task = await run_in_threadpool(enqueue_task, celery.tasks["src.tasks.run_gold_kalman"],
        args=[run_id], run_id=run_id, config={"policy": config.model_dump(mode="json"),
        "policy_hash": config.policy_hash(), "dataset_sha256": dataset.sha256},
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
    return run_to_dict(await checked(request, run_id))


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
                   limit: int = Query(2000, ge=1, le=10000), offset: int = Query(0, ge=0)):
    await checked(request, run_id)
    rows = await run_in_threadpool(query_rows, "market", run_id, method=method, limit=limit + 1, offset=offset, compact=True)
    return {"items": rows[:limit], "next_offset": offset + limit if len(rows) > limit else None}


@router.get("/api/v1/gold-kalman/runs/{run_id}/snapshot")
async def snapshot(request: Request, run_id: uuid.UUID, decision_time: AwareDatetime, method: Method = "scheduled"):
    await checked(request, run_id)
    rows = await run_in_threadpool(query_rows, "scores", run_id, method=method, decision_time=decision_time, limit=100)
    rows.sort(key=lambda row: row["z_score"])
    return {"items": rows}


@router.get("/api/v1/gold-kalman/runs/{run_id}/history")
async def history(request: Request, run_id: uuid.UUID, symbol: str, method: Method = "scheduled",
                  limit: int = Query(2000, ge=1, le=10000), offset: int = Query(0, ge=0)):
    await checked(request, run_id)
    rows = await run_in_threadpool(query_rows, "scores", run_id, method=method, symbol=symbol, limit=limit + 1, offset=offset)
    return {"items": rows[:limit], "next_offset": offset + limit if len(rows) > limit else None}


@router.get("/api/v1/gold-kalman/runs/{run_id}/export.csv")
async def export(request: Request, run_id: uuid.UUID, kind: Literal["scores", "market", "outcomes"] = "scores", method: Method = "scheduled"):
    run = await checked(request, run_id)
    def content():
        yield "# " + json.dumps({"run_id": str(run_id), "status": run.status, **run.config}, ensure_ascii=False) + "\n"
        yield from stream_csv(kind, run_id, method)
    return StreamingResponse(content(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="gold-{run_id}-{kind}.csv"'})
