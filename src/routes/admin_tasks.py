from datetime import date

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request

from src.celery_app import celery
from src.services.operation_runs import enqueue_task, get_run_by_task_id, run_to_dict
from src.tasks import (
    backfill_bond_order_books_task,
    backfill_bond_trades_task,
    backfill_option_order_books_task,
    backfill_option_trades_task,
    backfill_stock_order_books_task,
    backfill_stock_trades_task,
    backfill_yield_curves,
    compute_yield_curve_snapshot,
    sync_bond_instruments,
    sync_option_instruments,
    sync_stock_instruments,
    sync_ime_producers,
    backfill_ime_physical_trades,
)
from src.collectors.ime.service import ALL_HISTORY_START, enabled_producer_codes

router = APIRouter(prefix="/admin/tasks", tags=["admin-tasks"])


async def _require_admin(request: Request) -> None:
    auth_backend = getattr(request.app.state, "auth_backend", None)
    if not auth_backend:
        raise HTTPException(status_code=500, detail="Auth backend not configured")
    authenticated = await auth_backend.authenticate(request)
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")


class TaskSubmittedResponse(BaseModel):
    task_id: str
    status: str
    run_id: str
    collection_run_id: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None


class BackfillRequest(BaseModel):
    start_date: date = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="End date (YYYY-MM-DD)")

    def model_post_init(self, __context) -> None:
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        if (self.end_date - self.start_date).days > 731:
            raise ValueError("backfill is limited to 24 months")


class ImeBackfillRequest(BaseModel):
    producer_code: int = Field(..., gt=0)
    start_date: date | None = None
    end_date: date | None = None
    all_history: bool = False

    def model_post_init(self, __context) -> None:
        effective_start = ALL_HISTORY_START if self.all_history else self.start_date
        effective_end = self.end_date or (date.today() if self.all_history else None)
        if effective_start is None or effective_end is None:
            raise ValueError("start_date and end_date are required unless all_history is true")
        if effective_start > effective_end:
            raise ValueError("start_date must not be after end_date")


def _submitted(task, request: Request, *, body: BackfillRequest | None = None) -> TaskSubmittedResponse:
    kwargs = {}
    if body is not None:
        kwargs = {
            "start_date_str": body.start_date.isoformat(),
            "end_date_str": body.end_date.isoformat(),
        }
    row, async_result = enqueue_task(
        task,
        kwargs=kwargs,
        trigger="manual",
        created_by=request.session.get("user") or "admin",
    )
    identifier = str(row.run_id)
    return TaskSubmittedResponse(
        task_id=async_result.id,
        status="queued",
        run_id=identifier,
        collection_run_id=identifier if row.family == "collection" else None,
    )


@router.post("/sync-bond-instruments", response_model=TaskSubmittedResponse)
async def api_sync_bond_instruments(request: Request):
    await _require_admin(request)
    return _submitted(sync_bond_instruments, request)


@router.post("/backfill-bond-order-books", response_model=TaskSubmittedResponse)
async def api_backfill_bond_order_books(request: Request, body: BackfillRequest):
    await _require_admin(request)
    return _submitted(backfill_bond_order_books_task, request, body=body)


@router.post("/backfill-bond-trades", response_model=TaskSubmittedResponse)
async def api_backfill_bond_trades(request: Request, body: BackfillRequest):
    await _require_admin(request)
    return _submitted(backfill_bond_trades_task, request, body=body)


@router.post("/sync-option-instruments", response_model=TaskSubmittedResponse)
async def api_sync_option_instruments(request: Request):
    await _require_admin(request)
    return _submitted(sync_option_instruments, request)


@router.post("/sync-stock-instruments", response_model=TaskSubmittedResponse)
async def api_sync_stock_instruments(request: Request):
    await _require_admin(request)
    return _submitted(sync_stock_instruments, request)


@router.post("/sync-ime-producers", response_model=TaskSubmittedResponse)
async def api_sync_ime_producers(request: Request):
    await _require_admin(request)
    return _submitted(sync_ime_producers, request)


@router.post("/backfill-ime-physical-trades", response_model=TaskSubmittedResponse)
async def api_backfill_ime_physical_trades(request: Request, body: ImeBackfillRequest):
    await _require_admin(request)
    if body.producer_code not in set(enabled_producer_codes()):
        raise HTTPException(status_code=422, detail="producer must be enabled")
    start = ALL_HISTORY_START if body.all_history else body.start_date
    end = body.end_date or date.today()
    assert start is not None
    kwargs = {
        "producer_code": body.producer_code,
        "start_date_str": start.isoformat(),
        "end_date_str": end.isoformat(),
        "all_history": body.all_history,
    }
    row, async_result = enqueue_task(
        backfill_ime_physical_trades,
        kwargs=kwargs,
        trigger="manual",
        created_by=request.session.get("user") or "admin",
        start_date=start,
        end_date=end,
    )
    return TaskSubmittedResponse(
        task_id=async_result.id,
        status="queued",
        run_id=str(row.run_id),
        collection_run_id=str(row.run_id),
    )


@router.post("/backfill-stock-order-books", response_model=TaskSubmittedResponse)
async def api_backfill_stock_order_books(request: Request, body: BackfillRequest):
    await _require_admin(request)
    return _submitted(backfill_stock_order_books_task, request, body=body)


@router.post("/backfill-stock-trades", response_model=TaskSubmittedResponse)
async def api_backfill_stock_trades(request: Request, body: BackfillRequest):
    await _require_admin(request)
    return _submitted(backfill_stock_trades_task, request, body=body)


@router.post("/backfill-option-order-books", response_model=TaskSubmittedResponse)
async def api_backfill_option_order_books(request: Request, body: BackfillRequest):
    await _require_admin(request)
    return _submitted(backfill_option_order_books_task, request, body=body)


@router.post("/backfill-option-trades", response_model=TaskSubmittedResponse)
async def api_backfill_option_trades(request: Request, body: BackfillRequest):
    await _require_admin(request)
    return _submitted(backfill_option_trades_task, request, body=body)


@router.post("/compute-yield-curve-snapshot", response_model=TaskSubmittedResponse)
async def api_compute_yield_curve_snapshot(request: Request):
    await _require_admin(request)
    return _submitted(compute_yield_curve_snapshot, request)


@router.post("/backfill-yield-curves", response_model=TaskSubmittedResponse)
async def api_backfill_yield_curves(request: Request, body: BackfillRequest):
    await _require_admin(request)
    return _submitted(backfill_yield_curves, request, body=body)


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def api_task_status(request: Request, task_id: str):
    await _require_admin(request)
    operation = get_run_by_task_id(task_id)
    if operation is not None:
        data = run_to_dict(operation)
        return TaskStatusResponse(
            task_id=task_id,
            status=operation.status,
            result=data.get("result") or None,
            error=operation.error,
        )
    async_result: AsyncResult = AsyncResult(task_id, app=celery)
    resp = TaskStatusResponse(task_id=task_id, status=async_result.status)
    if async_result.successful():
        resp.result = async_result.result
    elif async_result.failed():
        resp.error = str(async_result.result)
    return resp
