from datetime import date

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request

from src.celery_app import celery
from src.tasks import (
    backfill_order_books_task,
    backfill_trades_task,
    sync_bond_instruments,
)

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


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None


class BackfillRequest(BaseModel):
    start_date: date = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="End date (YYYY-MM-DD)")


@router.post("/sync-instruments", response_model=TaskSubmittedResponse)
async def api_sync_instruments(request: Request):
    await _require_admin(request)
    task = sync_bond_instruments.delay()
    return TaskSubmittedResponse(task_id=task.id, status=task.status)


@router.post("/backfill-order-books", response_model=TaskSubmittedResponse)
async def api_backfill_order_books(request: Request, body: BackfillRequest):
    await _require_admin(request)
    task = backfill_order_books_task.delay(
        start_date_str=body.start_date.isoformat(),
        end_date_str=body.end_date.isoformat(),
    )
    return TaskSubmittedResponse(task_id=task.id, status=task.status)


@router.post("/backfill-trades", response_model=TaskSubmittedResponse)
async def api_backfill_trades(request: Request, body: BackfillRequest):
    await _require_admin(request)
    task = backfill_trades_task.delay(
        start_date_str=body.start_date.isoformat(),
        end_date_str=body.end_date.isoformat(),
    )
    return TaskSubmittedResponse(task_id=task.id, status=task.status)


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def api_task_status(request: Request, task_id: str):
    await _require_admin(request)
    async_result: AsyncResult = AsyncResult(task_id, app=celery)
    resp = TaskStatusResponse(task_id=task_id, status=async_result.status)
    if async_result.successful():
        resp.result = async_result.result
    elif async_result.failed():
        resp.error = str(async_result.result)
    return resp