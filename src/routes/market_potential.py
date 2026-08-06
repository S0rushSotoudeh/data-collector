from datetime import date

from fastapi import APIRouter, Query
from starlette.requests import Request

from src.db.clickhouse.iv_surface import coverage, market_potential, market_potential_summary
from src.routes.admin_tasks import _require_admin
from src.routes.iv_surface import _csv_response

router = APIRouter(prefix="/api/v1/options/market-potential", tags=["option-market-potential"])


@router.get("/coverage")
async def potential_coverage(request: Request):
    await _require_admin(request)
    return await coverage()


@router.get("/summary")
async def potential_summary(request: Request, start_date: date | None = None, end_date: date | None = None):
    await _require_admin(request)
    return await market_potential_summary(start_date, end_date)


async def _section(request: Request, section: str, start_date: date | None, end_date: date | None, limit: int):
    await _require_admin(request)
    return {"items": await market_potential(section, start_date, end_date, limit)}


@router.get("/timeseries")
async def potential_timeseries(request: Request, start_date: date | None = None, end_date: date | None = None, limit: int = Query(5000, ge=1, le=50000)):
    return await _section(request, "timeseries", start_date, end_date, limit)


@router.get("/contracts")
async def potential_contracts(request: Request, start_date: date | None = None, end_date: date | None = None, limit: int = Query(1000, ge=1, le=10000)):
    return await _section(request, "contracts", start_date, end_date, limit)


@router.get("/pairs")
async def potential_pairs(request: Request, start_date: date | None = None, end_date: date | None = None, limit: int = Query(1000, ge=1, le=10000)):
    return await _section(request, "pairs", start_date, end_date, limit)


@router.get("/export.csv")
async def potential_export(request: Request, start_date: date | None = None, end_date: date | None = None):
    await _require_admin(request)
    rows = await market_potential("contracts", start_date, end_date, 50000)
    return _csv_response("option-market-potential.csv", list(rows[0]) if rows else ["trade_date"], rows)
