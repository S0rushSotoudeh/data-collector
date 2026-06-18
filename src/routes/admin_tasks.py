from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request

from src.collectors.bond.instrument_sync import sync_instruments_to_pg
from src.collectors.bond.order_book_fetcher import (
    get_instrument_codes_active_in_range,
    backfill_order_books as backfill_for_range,
)

router = APIRouter(prefix="/admin/tasks", tags=["admin-tasks"])


async def _require_admin(request: Request) -> None:
    auth_backend = getattr(request.app.state, "auth_backend", None)
    if not auth_backend:
        raise HTTPException(status_code=500, detail="Auth backend not configured")
    authenticated = await auth_backend.authenticate(request)
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")


class SyncInstrumentsResponse(BaseModel):
    synced: int
    errors: list[str]


class BackfillRequest(BaseModel):
    start_date: date = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="End date (YYYY-MM-DD)")


class BackfillResponse(BaseModel):
    total_days_tried: int
    total_rows: int
    errors: list[str]
    instrument_count: int


@router.post("/sync-instruments", response_model=SyncInstrumentsResponse)
async def api_sync_instruments(request: Request):
    await _require_admin(request)
    try:
        result = await sync_instruments_to_pg()
        return SyncInstrumentsResponse(
            synced=result["synced"],
            errors=[str(e) for e in result["errors"]],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backfill-order-books", response_model=BackfillResponse)
async def api_backfill_order_books(request: Request, body: BackfillRequest):
    await _require_admin(request)
    try:
        codes = await get_instrument_codes_active_in_range(
            body.start_date, body.end_date
        )
        result = await backfill_for_range(
            start_date=body.start_date,
            end_date=body.end_date,
            instrument_codes=codes,
        )
        return BackfillResponse(
            total_days_tried=result["total_days_tried"],
            total_rows=result["total_rows"],
            errors=[str(e) for e in result["errors"]],
            instrument_count=len(codes),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))