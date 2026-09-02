from datetime import date
import math

from fastapi import APIRouter, HTTPException, Query

from src.db.clickhouse.query import (
    get_gold_order_book_micro_price_intraday,
    get_stock_trades_daily,
)
from src.routes.yield_curve import _validate_hhmmss

router = APIRouter(prefix="/api/v1", tags=["gold-analytics"])


@router.get("/gold-analytics/compare/intraday")
async def api_gold_compare_intraday(
    instrument1: str = Query(..., description="First instrument code"),
    instrument2: str = Query(..., description="Second instrument code"),
    date: date = Query(..., description="Trade date"),
    from_time: int | None = Query(default=None, description="HHMMSS start"),
    to_time: int | None = Query(default=None, description="HHMMSS end"),
):
    if from_time is not None and isinstance(from_time, int):
        try:
            _validate_hhmmss(from_time, "from_time")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    else:
        from_time = None

    if to_time is not None and isinstance(to_time, int):
        try:
            _validate_hhmmss(to_time, "to_time")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    else:
        to_time = None

    effective_from_time = from_time if from_time is not None else 113000

    points1 = await get_gold_order_book_micro_price_intraday(
        instrument_code=instrument1,
        trade_date=date,
        from_time=effective_from_time,
        to_time=to_time,
        bucket_seconds=5,
        price_type="best",
    )
    points2 = await get_gold_order_book_micro_price_intraday(
        instrument_code=instrument2,
        trade_date=date,
        from_time=effective_from_time,
        to_time=to_time,
        bucket_seconds=5,
        price_type="best",
    )
    return {
        "trade_date": str(date),
        "instrument1": {"code": instrument1, "points": points1},
        "instrument2": {"code": instrument2, "points": points2},
    }


@router.get("/gold-analytics/normalized-spread/intraday")
async def api_gold_normalized_spread_intraday(
    instrument1: str = Query(..., description="First instrument code"),
    instrument2: str = Query(..., description="Second instrument code"),
    date: date = Query(..., description="Trade date"),
    from_time: int | None = Query(default=None, description="HHMMSS start"),
    to_time: int | None = Query(default=None, description="HHMMSS end"),
):
    if from_time is not None and isinstance(from_time, int):
        try:
            _validate_hhmmss(from_time, "from_time")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    else:
        from_time = None

    if to_time is not None and isinstance(to_time, int):
        try:
            _validate_hhmmss(to_time, "to_time")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    else:
        to_time = None

    effective_from_time = from_time if from_time is not None else 113000

    points1 = await get_gold_order_book_micro_price_intraday(
        instrument_code=instrument1,
        trade_date=date,
        from_time=effective_from_time,
        to_time=to_time,
        bucket_seconds=5,
        price_type="best",
    )
    points2 = await get_gold_order_book_micro_price_intraday(
        instrument_code=instrument2,
        trade_date=date,
        from_time=effective_from_time,
        to_time=to_time,
        bucket_seconds=5,
        price_type="best",
    )

    # Find first valid prices to use as log-return baseline
    init_p1_bid = next((p["best_bid"] for p in points1 if p.get("best_bid", 0) > 0), None)
    init_p1_ask = next((p["best_ask"] for p in points1 if p.get("best_ask", 0) > 0), None)
    init_p2_bid = next((p["best_bid"] for p in points2 if p.get("best_bid", 0) > 0), None)
    init_p2_ask = next((p["best_ask"] for p in points2 if p.get("best_ask", 0) > 0), None)

    def to_log_return(points: list, bid_init: float | None, ask_init: float | None) -> list[dict]:
        out = []
        for p in points:
            bid = p.get("best_bid", 0)
            ask = p.get("best_ask", 0)
            entry: dict = {"t": p["trade_time"]}
            if bid > 0 and bid_init:
                entry["bid"] = round(math.log(bid / bid_init), 5)
            if ask > 0 and ask_init:
                entry["ask"] = round(math.log(ask / ask_init), 5)
            if "bid" in entry or "ask" in entry:
                out.append(entry)
        return out

    return {
        "trade_date": str(date),
        "instrument1": {"code": instrument1, "points": to_log_return(points1, init_p1_bid, init_p1_ask)},
        "instrument2": {"code": instrument2, "points": to_log_return(points2, init_p2_bid, init_p2_ask)},
    }



@router.get("/gold-analytics/compare/daily")
async def api_gold_compare_daily(
    instrument1: str = Query(..., description="First instrument code"),
    instrument2: str = Query(..., description="Second instrument code"),
    frm: date = Query(..., alias="from", description="From date"),
    to: date = Query(..., description="To date"),
):
    days1 = await get_stock_trades_daily(
        instrument_code=instrument1,
        from_date=frm,
        to_date=to,
    )
    days2 = await get_stock_trades_daily(
        instrument_code=instrument2,
        from_date=frm,
        to_date=to,
    )
    return {
        "from": str(frm),
        "to": str(to),
        "instrument1": {"code": instrument1, "days": days1},
        "instrument2": {"code": instrument2, "days": days2},
    }
