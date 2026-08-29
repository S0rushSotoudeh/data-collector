from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.db.clickhouse.gold import (
    get_gold_latest_order_book,
    get_gold_ohlcv,
    get_gold_order_book_history,
    get_gold_trades_daily,
    get_gold_trades_intraday,
    get_gold_vwap,
)
from src.routes.yield_curve import _validate_hhmmss

router = APIRouter(prefix="/api/v1", tags=["gold"])


@router.get("/gold/order-book/latest")
async def api_gold_order_book_latest(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
):
    rows = await get_gold_latest_order_book(
        instrument_code=instrument,
        trade_date=date,
    )
    return {
        "instrument": instrument,
        "trade_date": str(date),
        "rows": rows,
    }


@router.get("/gold/order-book/history")
async def api_gold_order_book_history(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
):
    rows = await get_gold_order_book_history(
        instrument_code=instrument,
        trade_date=date,
    )
    return {
        "instrument": instrument,
        "trade_date": str(date),
        "rows": rows,
    }


@router.get("/gold/trades/intraday")
async def api_gold_trades_intraday(
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

    points = await get_gold_trades_intraday(
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


@router.get("/gold/trades/daily")
async def api_gold_trades_daily(
    instrument: str = Query(..., description="Instrument code"),
    frm: date = Query(..., alias="from", description="From date"),
    to: date = Query(..., description="To date"),
):
    days = await get_gold_trades_daily(
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


@router.get("/gold/vwap")
async def api_gold_vwap(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
):
    result = await get_gold_vwap(
        instrument_code=instrument,
        trade_date=date,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No trades found")
    return {
        "instrument": instrument,
        "trade_date": str(date),
        **result,
    }


@router.get("/gold/ohlcv")
async def api_gold_ohlcv(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
):
    rows = await get_gold_ohlcv(
        instrument_code=instrument,
        trade_date=date,
    )
    return {
        "instrument": instrument,
        "trade_date": str(date),
        "candles": rows,
    }
