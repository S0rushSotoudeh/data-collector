from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.db.clickhouse.stock import (
    get_stock_daily_spread,
    get_stock_latest_order_book,
    get_stock_ohlcv,
    get_stock_order_book_history,
    get_stock_trades_daily,
    get_stock_trades_intraday,
    get_stock_trades_ranking,
    get_stock_vwap,
)
from src.routes.yield_curve import _validate_hhmmss

router = APIRouter(prefix="/api/v1", tags=["stocks"])


@router.get("/stocks/order-book/latest")
async def api_stock_order_book_latest(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
):
    rows = await get_stock_latest_order_book(
        instrument_code=instrument,
        trade_date=date,
    )
    return {
        "instrument": instrument,
        "trade_date": str(date),
        "rows": rows,
    }


@router.get("/stocks/order-book/history")
async def api_stock_order_book_history(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
):
    rows = await get_stock_order_book_history(
        instrument_code=instrument,
        trade_date=date,
    )
    return {
        "instrument": instrument,
        "trade_date": str(date),
        "rows": rows,
    }


@router.get("/stocks/trades/intraday")
async def api_stock_trades_intraday(
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

    points = await get_stock_trades_intraday(
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


@router.get("/stocks/trades/daily")
async def api_stock_trades_daily(
    instrument: str = Query(..., description="Instrument code"),
    frm: date = Query(..., alias="from", description="From date"),
    to: date = Query(..., description="To date"),
):
    days = await get_stock_trades_daily(
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


@router.get("/stocks/trades/ranking")
async def api_stock_trades_ranking(
    frm: date = Query(..., alias="from", description="From date"),
    to: date = Query(..., description="To date"),
):
    rows = await get_stock_trades_ranking(from_date=frm, to_date=to)
    return {"from": str(frm), "to": str(to), "rows": rows}


@router.get("/stocks/vwap")
async def api_stock_vwap(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
):
    result = await get_stock_vwap(
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


@router.get("/stocks/ohlcv")
async def api_stock_ohlcv(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
):
    rows = await get_stock_ohlcv(
        instrument_code=instrument,
        trade_date=date,
    )
    return {
        "instrument": instrument,
        "trade_date": str(date),
        "candles": rows,
    }


@router.get("/stocks/spread")
async def api_stock_spread(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
):
    result = await get_stock_daily_spread(
        instrument_code=instrument,
        trade_date=date,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No order book data found")
    return {
        "instrument": instrument,
        "trade_date": str(date),
        **result,
    }
