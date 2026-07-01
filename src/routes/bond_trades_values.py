from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.db.clickhouse.query import (
    get_bond_trades_daily,
    get_bond_trades_intraday,
    get_bond_trades_ranking,
)
from src.routes.yield_curve import _validate_hhmmss

router = APIRouter(prefix="/api/v1", tags=["bond-trades-values"])


@router.get("/bond-trades-values/intraday")
async def api_bond_trades_intraday(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
    from_time: int | None = Query(None, description="HHMMSS start"),
    to_time: int | None = Query(None, description="HHMMSS end"),
    limit: int = Query(2000, ge=1, le=20000, description="Max points"),
):
    if from_time is not None:
        try:
            _validate_hhmmss(from_time, "from_time")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    if to_time is not None:
        try:
            _validate_hhmmss(to_time, "to_time")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    points = await get_bond_trades_intraday(
        instrument_code=instrument,
        trade_date=date,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
    )
    return {
        "instrument": instrument,
        "trade_date": str(date),
        "limit": limit,
        "points": points,
    }


@router.get("/bond-trades-values/daily")
async def api_bond_trades_daily(
    instrument: str = Query(..., description="Instrument code"),
    frm: date = Query(..., alias="from", description="From date"),
    to: date = Query(..., description="To date"),
):
    days = await get_bond_trades_daily(
        instrument_code=instrument,
        from_date=frm,
        to_date=to,
    )
    return {
        "instrument": instrument,
        "from": str(frm),
        "to": str(to),
        "days": days,
    }


@router.get("/bond-trades-values/ranking")
async def api_bond_trades_ranking(
    frm: date = Query(..., alias="from", description="From date"),
    to: date = Query(..., description="To date"),
):
    rows = await get_bond_trades_ranking(from_date=frm, to_date=to)
    return {"from": str(frm), "to": str(to), "rows": rows}
