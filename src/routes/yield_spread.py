import math
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.db.clickhouse.query import (
    get_yield_spread_daily,
    get_yield_spread_intraday,
)
from src.routes.yield_curve import _validate_hhmmss, _validate_side

router = APIRouter(prefix="/api/v1", tags=["yield-spread"])


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[int(pos)]
    v_lo = sorted_vals[lo]
    v_hi = sorted_vals[hi]
    return v_lo + (v_hi - v_lo) * (pos - lo)


def _box_stats(values: list[float]) -> dict[str, Any]:
    vals = sorted(v for v in values if v is not None and not math.isnan(v))
    n = len(vals)
    if n == 0:
        return {"box": None, "mean": None, "n": 0, "outliers": []}
    q1 = _quantile(vals, 0.25)
    median = _quantile(vals, 0.50)
    q3 = _quantile(vals, 0.75)
    iqr = q3 - q1
    lo_fence = q1 - 1.5 * iqr
    hi_fence = q3 + 1.5 * iqr
    outliers: list[float] = []
    in_range: list[float] = []
    for v in vals:
        if v < lo_fence or v > hi_fence:
            outliers.append(v)
        else:
            in_range.append(v)
    # whisker ends: most extreme in-range values (ECharts box[0]/box[4]).
    if in_range:
        whisker_lo = in_range[0]
        whisker_hi = in_range[-1]
    else:
        whisker_lo = q1
        whisker_hi = q3
    mean = sum(vals) / n
    return {
        "box": [whisker_lo, q1, median, q3, whisker_hi],
        "mean": mean,
        "n": n,
        "outliers": outliers,
    }


def _aggregate_daily(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple, list[float]] = {}
    order: list[tuple] = []
    for p in points:
        key = (p["trade_date"], p["curve_side"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p["spread_bps"])

    days: list[dict[str, Any]] = []
    for key in order:
        trade_date, curve_side = key
        stats = _box_stats(groups[key])
        days.append({
            "trade_date": trade_date,
            "curve_side": curve_side,
            **stats,
        })
    return days


@router.get("/yield-spread/intraday")
async def api_yield_spread_intraday(
    instrument: str = Query(..., description="Instrument code"),
    date: date = Query(..., description="Trade date"),
    side: str = Query("both", description="bid / ask / both"),
    from_time: int | None = Query(None, description="HHMMSS start"),
    to_time: int | None = Query(None, description="HHMMSS end"),
):
    try:
        _validate_side(side)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
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

    points = await get_yield_spread_intraday(
        instrument_code=instrument,
        trade_date=date,
        curve_side=side,
        from_time=from_time,
        to_time=to_time,
    )
    return {
        "instrument": instrument,
        "trade_date": str(date),
        "side": side,
        "points": points,
    }


@router.get("/yield-spread/daily")
async def api_yield_spread_daily(
    instrument: str = Query(..., description="Instrument code"),
    frm: date = Query(..., alias="from", description="From date"),
    to: date = Query(..., description="To date"),
    side: str = Query("both", description="bid / ask / both"),
):
    try:
        _validate_side(side)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    points = await get_yield_spread_daily(
        instrument_code=instrument,
        from_date=frm,
        to_date=to,
        curve_side=side,
    )
    days = _aggregate_daily(points)
    return {
        "instrument": instrument,
        "from": str(frm),
        "to": str(to),
        "side": side,
        "days": days,
    }
