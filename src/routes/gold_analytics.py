from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.analytics.gold_kalman import run_gold_kalman_filter
from src.db.clickhouse.query import (
    get_gold_order_book_micro_price_intraday,
    get_gold_trades_comparison_intraday,
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

    points1 = await get_gold_trades_comparison_intraday(
        instrument_code=instrument1,
        trade_date=date,
        from_time=from_time,
        to_time=to_time,
        bucket_seconds=5,
    )
    points2 = await get_gold_trades_comparison_intraday(
        instrument_code=instrument2,
        trade_date=date,
        from_time=from_time,
        to_time=to_time,
        bucket_seconds=5,
    )
    return {
        "trade_date": str(date),
        "instrument1": {"code": instrument1, "points": points1},
        "instrument2": {"code": instrument2, "points": points2},
    }


@router.get("/gold-analytics/kalman-arbitrage/intraday")
async def api_gold_kalman_arbitrage_intraday(
    instrument1: str = Query(..., description="First instrument code (observed Y)"),
    instrument2: str = Query(..., description="Second instrument code (predictor X)"),
    date: date = Query(..., description="Trade date"),
    price_source: str = Query(
        default="orderbook_micro",
        description="Price source: orderbook_micro, orderbook_mid, or trades",
    ),
    from_time: int | None = Query(default=None, description="HHMMSS start"),
    to_time: int | None = Query(default=None, description="HHMMSS end"),
    delta: float = Query(default=1e-4, ge=1e-7, le=1e-1, description="Process variance delta"),
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

    if price_source == "orderbook_mid":
        points1 = await get_gold_order_book_micro_price_intraday(
            instrument_code=instrument1,
            trade_date=date,
            from_time=from_time,
            to_time=to_time,
            bucket_seconds=5,
            price_type="mid",
        )
        points2 = await get_gold_order_book_micro_price_intraday(
            instrument_code=instrument2,
            trade_date=date,
            from_time=from_time,
            to_time=to_time,
            bucket_seconds=5,
            price_type="mid",
        )
    elif price_source == "trades":
        points1 = await get_gold_trades_comparison_intraday(
            instrument_code=instrument1,
            trade_date=date,
            from_time=from_time,
            to_time=to_time,
            bucket_seconds=5,
        )
        points2 = await get_gold_trades_comparison_intraday(
            instrument_code=instrument2,
            trade_date=date,
            from_time=from_time,
            to_time=to_time,
            bucket_seconds=5,
        )
    else:  # orderbook_micro (default)
        points1 = await get_gold_order_book_micro_price_intraday(
            instrument_code=instrument1,
            trade_date=date,
            from_time=from_time,
            to_time=to_time,
            bucket_seconds=5,
            price_type="micro",
        )
        points2 = await get_gold_order_book_micro_price_intraday(
            instrument_code=instrument2,
            trade_date=date,
            from_time=from_time,
            to_time=to_time,
            bucket_seconds=5,
            price_type="micro",
        )

    # Time alignment with forward fill
    time_map: dict[int, dict[str, float]] = {}
    for p in points1:
        t = p["trade_time"]
        if t not in time_map:
            time_map[t] = {}
        time_map[t]["p1"] = p["price"]
    for p in points2:
        t = p["trade_time"]
        if t not in time_map:
            time_map[t] = {}
        time_map[t]["p2"] = p["price"]

    all_times = sorted(time_map.keys())
    aligned_times: list[int] = []
    prices1: list[float] = []
    prices2: list[float] = []

    last_p1: float | None = None
    last_p2: float | None = None

    for t in all_times:
        if "p1" in time_map[t] and last_p1 is None:
            last_p1 = time_map[t]["p1"]
        if "p2" in time_map[t] and last_p2 is None:
            last_p2 = time_map[t]["p2"]
        if last_p1 is not None and last_p2 is not None:
            break

    if last_p1 is not None and last_p2 is not None:
        for t in all_times:
            if "p1" in time_map[t]:
                last_p1 = time_map[t]["p1"]
            if "p2" in time_map[t]:
                last_p2 = time_map[t]["p2"]
            aligned_times.append(t)
            prices1.append(last_p1)
            prices2.append(last_p2)

    kalman_res = run_gold_kalman_filter(
        prices1=prices1,
        prices2=prices2,
        times=aligned_times,
        delta=delta,
    )

    return {
        "trade_date": str(date),
        "instrument1": instrument1,
        "instrument2": instrument2,
        "price_source": price_source,
        "results": kalman_res,
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
