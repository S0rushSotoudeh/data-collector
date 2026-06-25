from datetime import date

from fastapi import APIRouter, Query

from src.analytics.yield_curve import classify_signal
from src.db.clickhouse.query import (
    get_latest_yield_curve,
    get_yield_curve_bonds,
    get_yield_curve_fits,
)

router = APIRouter(prefix="/api/v1", tags=["yield-curve"])

_VALID_SIDES = {"bid", "ask", "both"}
_DEFAULT_THRESHOLD_BPS = 50.0


def _validate_side(side: str) -> str:
    if side not in _VALID_SIDES:
        raise ValueError(f"side must be one of {_VALID_SIDES}, got {side!r}")
    return side


def _validate_hhmmss(value: int, name: str) -> int:
    if not 0 <= value <= 235959:
        raise ValueError(f"{name} must be a HHMMSS integer in [0, 235959], got {value}")
    return value


@router.get("/yield-curve/curves")
async def api_yield_curves(
    date: date = Query(..., description="Trade date"),
    side: str = Query("both", description="bid / ask / both"),
    from_time: int | None = Query(None, description="HHMMSS start"),
    to_time: int | None = Query(None, description="HHMMSS end"),
):
    _validate_side(side)
    if from_time is not None:
        _validate_hhmmss(from_time, "from_time")
    if to_time is not None:
        _validate_hhmmss(to_time, "to_time")
    rows = await get_yield_curve_fits(
        trade_date=date, curve_side=side, from_time=from_time, to_time=to_time
    )
    return {"trade_date": str(date), "curves": rows}


@router.get("/yield-curve/curves/latest")
async def api_latest_curve(
    side: str = Query("both", description="bid / ask / both"),
):
    _validate_side(side)
    rows = await get_latest_yield_curve(curve_side=side)
    result: dict = {}
    for r in rows:
        result[r["curve_side"]] = r
    ts = rows[0]["trade_date"].isoformat() if rows else None
    return {
        "trade_date": ts,
        "curves": result,
    }


@router.get("/yield-curve/bonds")
async def api_curve_bonds(
    date: date = Query(..., description="Trade date"),
    time: int = Query(..., description="HHMMSS time"),
    side: str = Query("both", description="bid / ask / both"),
):
    _validate_side(side)
    _validate_hhmmss(time, "time")
    rows = await get_yield_curve_bonds(
        trade_date=date, trade_time=time, curve_side=side
    )
    return {"trade_date": str(date), "trade_time": time, "bonds": rows}


@router.get("/yield-curve/arbitrage")
async def api_arbitrage(
    date: date = Query(..., description="Trade date"),
    time: int = Query(..., description="HHMMSS time"),
    side: str = Query("both", description="bid / ask / both"),
    threshold_bps: float = Query(
        _DEFAULT_THRESHOLD_BPS, ge=0, description="Threshold in bps"
    ),
):
    _validate_side(side)
    _validate_hhmmss(time, "time")
    rows = await get_yield_curve_bonds(
        trade_date=date, trade_time=time, curve_side=side
    )
    flagged = []
    for r in rows:
        spread = r.get("spread_bps")
        if spread is None:
            continue
        signal = classify_signal(spread, threshold_bps)
        if signal in ("cheap", "rich") and abs(spread) >= threshold_bps:
            r["signal"] = signal
            flagged.append(r)
    flagged.sort(key=lambda r: abs(r["spread_bps"]), reverse=True)
    return {
        "trade_date": str(date),
        "trade_time": time,
        "threshold_bps": threshold_bps,
        "bonds": flagged,
    }
