import asyncio
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.db.clickhouse.deposit_certificates import SYMBOLS, intraday_best_quotes
from src.db.clickhouse.query import (
    get_gold_order_book_micro_price_intraday,
    get_stock_trades_daily,
)
from src.routes.yield_curve import _validate_hhmmss

router = APIRouter(prefix="/api/v1", tags=["gold-analytics"])

GOLD_ETF_TRADING_START = 120000
GOLD_TRADING_END = 180000


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

    effective_from_time = max(from_time or GOLD_ETF_TRADING_START, GOLD_ETF_TRADING_START)

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

    effective_from_time = max(from_time or GOLD_ETF_TRADING_START, GOLD_ETF_TRADING_START)
    effective_to_time = min(to_time or GOLD_TRADING_END, GOLD_TRADING_END)
    if effective_from_time > effective_to_time:
        raise HTTPException(status_code=422, detail="Requested time range is outside the 12:00–18:00 trading session")

    points1, points2, gold_bar, gold_coin = await asyncio.gather(
        get_gold_order_book_micro_price_intraday(
            instrument_code=instrument1, trade_date=date, from_time=effective_from_time,
            to_time=effective_to_time, bucket_seconds=5, price_type="best",
        ),
        get_gold_order_book_micro_price_intraday(
            instrument_code=instrument2, trade_date=date, from_time=effective_from_time,
            to_time=effective_to_time, bucket_seconds=5, price_type="best",
        ),
        intraday_best_quotes(SYMBOLS[0], date, effective_from_time, effective_to_time),
        intraday_best_quotes(SYMBOLS[1], date, effective_from_time, effective_to_time),
    )

    def normalized(points: list[dict]) -> tuple[list[dict], dict[str, float | None]]:
        prices = [
            float(p[side])
            for p in points
            for side in ("best_bid", "best_ask")
            if p.get(side, 0) > 0
        ]
        if not prices:
            return [], {"min": None, "max": None}

        minimum, maximum = min(prices), max(prices)
        span = maximum - minimum
        out = []
        for p in points:
            bid = p.get("best_bid", 0)
            ask = p.get("best_ask", 0)
            entry: dict = {"t": p["trade_time"]}
            if bid > 0:
                entry.update(bid=round((bid - minimum) / span, 6) if span else 0.5, bid_price=bid)
            if ask > 0:
                entry.update(ask=round((ask - minimum) / span, 6) if span else 0.5, ask_price=ask)
            if "bid" in entry or "ask" in entry:
                out.append(entry)
        return out, {"min": minimum, "max": maximum}

    points1, scale1 = normalized(points1)
    points2, scale2 = normalized(points2)
    gold_bar, gold_bar_scale = normalized(gold_bar)
    gold_coin, gold_coin_scale = normalized(gold_coin)

    return {
        "trade_date": str(date),
        "instrument1": {"code": instrument1, "points": points1, "scale": scale1},
        "instrument2": {"code": instrument2, "points": points2, "scale": scale2},
        "certificates": [
            {"code": SYMBOLS[0], "points": gold_bar, "scale": gold_bar_scale},
            {"code": SYMBOLS[1], "points": gold_coin, "scale": gold_coin_scale},
        ],
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
