from __future__ import annotations

import csv
import io
import json
import uuid
from collections import defaultdict
from datetime import date, datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select
from starlette.requests import Request
from starlette.responses import StreamingResponse

from src.analytics.box_spread import BOX_CALCULATION_VERSION, LEGS, actions, calculate_maker_routes
from src.analytics.box_spread_config import BoxCalculatorRequest, BoxSpreadRunConfig
from src.analytics.depth import DepthBook, DepthLevel
from src.analytics.parity_engine import aligned_snapshots, hhmmss, time_from_hhmmss
from src.db.clickhouse import get_async_client
from src.db.clickhouse.box_spread import get_pricings, get_snapshots
from src.db.models.operations import OptionFeeSchedule, OptionPricingConvention
from src.db.models.option import OptionInstrument
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal
from src.routes.admin_tasks import _require_admin
from src.services.operation_runs import enqueue_task, get_run, list_runs, run_to_dict
from src.tasks import run_box_spread_analysis


router = APIRouter(tags=["box-spread"])
TEHRAN = ZoneInfo("Asia/Tehran")


def _side(item: OptionInstrument) -> str:
    return "call" if (item.option_type or "").lower() in {"call", "c"} else "put"


def _resolved_legs(
    options: list[OptionInstrument], lower_strike: float, upper_strike: float,
) -> tuple[dict[str, OptionInstrument], list[dict[str, str]]]:
    grouped: dict[tuple[float, str], list[OptionInstrument]] = defaultdict(list)
    for item in options:
        if item.strike_price is not None and (item.option_type or "").lower() in {"call", "c", "put", "p"}:
            grouped[(float(item.strike_price), _side(item))].append(item)
    resolved: dict[str, OptionInstrument] = {}
    errors: list[dict[str, str]] = []
    for leg, strike, side in (
        ("c1", lower_strike, "call"), ("p1", lower_strike, "put"),
        ("c2", upper_strike, "call"), ("p2", upper_strike, "put"),
    ):
        candidates = grouped.get((float(strike), side), [])
        if len(candidates) != 1:
            errors.append({"field": leg, "message": f"expected exactly one {side} at strike {strike}"})
        else:
            resolved[leg] = candidates[0]
    return resolved, errors


def _fee_market(stock: StockInstrument) -> str:
    market = {1: "tse", 2: "ifb"}.get(stock.market_code)
    if market is None:
        raise HTTPException(
            status_code=422,
            detail={"errors": [{"field": "underlying_instrument_code", "message": "unsupported underlying market"}]},
        )
    return market


def _fee_schedule_for(session, stock: StockInstrument, trade_date: date) -> OptionFeeSchedule:
    market = _fee_market(stock)
    schedules = session.execute(select(OptionFeeSchedule).where(
        OptionFeeSchedule.market == market,
        OptionFeeSchedule.effective_from <= trade_date,
        or_(OptionFeeSchedule.effective_to.is_(None), OptionFeeSchedule.effective_to >= trade_date),
    )).scalars().all()
    if len(schedules) != 1:
        raise HTTPException(
            status_code=422,
            detail={"errors": [{
                "field": "trade_date",
                "message": f"expected exactly one {market.upper()} option fee schedule for this date",
            }]},
        )
    return schedules[0]


def _validate_metadata(
    config: BoxSpreadRunConfig,
) -> tuple[OptionPricingConvention, StockInstrument, dict[str, OptionInstrument]]:
    with SessionLocal() as session:
        stock = session.get(StockInstrument, config.underlying_instrument_code)
        convention = session.get(OptionPricingConvention, config.pricing_convention_id)
        options = session.execute(select(OptionInstrument).where(
            OptionInstrument.underlying_instrument_code == config.underlying_instrument_code,
            OptionInstrument.expiry_date == config.expiry_date,
        )).scalars().all()
    errors: list[dict[str, str]] = []
    if stock is None:
        errors.append({"field": "underlying_instrument_code", "message": "unknown underlying"})
    if convention is None:
        errors.append({"field": "pricing_convention_id", "message": "unknown pricing convention"})
    elif not convention.approved or convention.approved_at is None:
        errors.append({"field": "pricing_convention_id", "message": "pricing convention is not approved"})
    elif convention.exercise_style.lower() not in {"european", "european-style"}:
        errors.append({"field": "pricing_convention_id", "message": "box analysis requires European exercise"})
    elif config.trade_date < convention.effective_from or (convention.effective_to and config.trade_date > convention.effective_to):
        errors.append({"field": "pricing_convention_id", "message": "pricing convention is not effective on trade date"})
    resolved, leg_errors = _resolved_legs(options, config.lower_strike, config.upper_strike)
    errors.extend(leg_errors)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    return convention, stock, resolved


def _calculator_metadata(
    config: BoxCalculatorRequest,
) -> tuple[StockInstrument, OptionPricingConvention, dict[str, OptionInstrument], OptionFeeSchedule]:
    with SessionLocal() as session:
        stock = session.get(StockInstrument, config.underlying_instrument_code)
        options = session.execute(select(OptionInstrument).where(
            OptionInstrument.underlying_instrument_code == config.underlying_instrument_code,
            OptionInstrument.expiry_date == config.expiry_date,
        )).scalars().all()
        resolved, errors = _resolved_legs(options, config.lower_strike, config.upper_strike)
        if stock is None:
            errors.append({"field": "underlying_instrument_code", "message": "unknown underlying"})
        conventions = session.execute(select(OptionPricingConvention).where(
            OptionPricingConvention.approved.is_(True),
            OptionPricingConvention.effective_from <= config.trade_date,
            or_(
                OptionPricingConvention.effective_to.is_(None),
                OptionPricingConvention.effective_to >= config.trade_date,
            ),
        )).scalars().all()
        conventions = [
            item for item in conventions
            if item.exercise_style.lower() in {"european", "european-style"}
        ]
        if len(conventions) != 1:
            errors.append({"field": "trade_date", "message": "expected exactly one approved European pricing convention"})
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        fee_schedule = _fee_schedule_for(session, stock, config.trade_date)
        return stock, conventions[0], resolved, fee_schedule


async def _validate_coverage(config: BoxSpreadRunConfig, legs: dict[str, OptionInstrument]) -> None:
    client = await get_async_client()
    result = await client.query(
        "SELECT uniqExact(instrument_code) FROM option_order_book FINAL "
        "WHERE trade_date = {day:Date} AND instrument_code IN {codes:Array(String)} AND depth_level = 1",
        parameters={"day": config.trade_date, "codes": [item.instrument_code for item in legs.values()]},
    )
    if not result.result_rows or int(result.result_rows[0][0]) != 4:
        raise HTTPException(status_code=422, detail={"errors": [{"field": "trade_date", "message": "all four legs require order-book coverage"}]})


@router.get("/api/v1/options/chain-choices")
async def chain_choices(
    request: Request, mode: Literal["box", "parity"] = "box", trade_date: date | None = None,
    underlying_instrument_code: str | None = None, expiry_date: date | None = None,
    lower_strike: float | None = None,
):
    await _require_admin(request)
    client = await get_async_client()
    dates_result = await client.query("SELECT DISTINCT trade_date FROM option_order_book ORDER BY trade_date DESC LIMIT 730")
    dates = [row[0].isoformat() for row in dates_result.result_rows]
    response: dict[str, Any] = {"dates": dates, "underlyings": [], "expiries": [], "lower_strikes": [], "upper_strikes": [], "pairs": [], "conventions": []}
    if trade_date is None:
        return response
    codes_result = await client.query(
        "SELECT DISTINCT instrument_code FROM option_order_book FINAL WHERE trade_date = {day:Date} AND depth_level = 1",
        parameters={"day": trade_date},
    )
    codes = [str(row[0]) for row in codes_result.result_rows]
    with SessionLocal() as session:
        options = session.execute(select(OptionInstrument).where(OptionInstrument.instrument_code.in_(codes))).scalars().all() if codes else []
        stocks = session.execute(select(StockInstrument)).scalars().all()
        conventions = session.execute(select(OptionPricingConvention).where(
            OptionPricingConvention.approved.is_(True)
        )).scalars().all()
    stock_labels = {item.instrument_code: item.symbol or item.instrument_code for item in stocks}
    pairs: dict[tuple[str, date, float], dict[str, Any]] = {}
    for item in options:
        if not item.underlying_instrument_code or item.expiry_date is None or item.strike_price is None:
            continue
        side = (item.option_type or "").lower()
        if side not in {"call", "c", "put", "p"}:
            continue
        key = (item.underlying_instrument_code, item.expiry_date, float(item.strike_price))
        pair = pairs.setdefault(key, {"underlying": key[0], "expiry": key[1], "strike": key[2]})
        pair["call" if side in {"call", "c"} else "put"] = item.instrument_code
    complete = [value for value in pairs.values() if "call" in value and "put" in value]
    chain_counts: dict[tuple[str, date], int] = defaultdict(int)
    for pair in complete:
        chain_counts[(pair["underlying"], pair["expiry"])] += 1
    minimum_pairs = 2 if mode == "box" else 1
    eligible = [
        pair for pair in complete
        if chain_counts[(pair["underlying"], pair["expiry"])] >= minimum_pairs
        and pair["underlying"] in stock_labels
    ]
    underlyings = sorted({pair["underlying"] for pair in eligible}, key=lambda code: stock_labels.get(code, code))
    response["underlyings"] = [{"code": code, "label": stock_labels.get(code, code)} for code in underlyings]
    if underlying_instrument_code:
        narrowed = [pair for pair in eligible if pair["underlying"] == underlying_instrument_code]
        response["expiries"] = sorted({pair["expiry"].isoformat() for pair in narrowed})
        if expiry_date:
            narrowed = [pair for pair in narrowed if pair["expiry"] == expiry_date]
            strikes = sorted({pair["strike"] for pair in narrowed})
            response["lower_strikes"] = strikes[:-1] if mode == "box" else strikes
            response["upper_strikes"] = [strike for strike in strikes if lower_strike is not None and strike > lower_strike]
            response["pairs"] = [{**pair, "expiry": pair["expiry"].isoformat()} for pair in narrowed]
    response["conventions"] = [{
        "id": str(item.convention_id), "name": item.name, "multiplier": item.multiplier,
        "tick_size": item.tick_size, "exercise_style": item.exercise_style,
    } for item in conventions if item.exercise_style.lower() in {"european", "european-style"}]
    return response


@router.post("/admin/tasks/run-box-spread")
async def create_box_spread_run(request: Request, config: BoxSpreadRunConfig):
    await _require_admin(request)
    convention, stock, legs = _validate_metadata(config)
    await _validate_coverage(config, legs)
    run_id = str(uuid.uuid4())
    total = len(aligned_snapshots(config.trade_date, config.session_start, config.session_end, config.interval_seconds))
    payload = config.model_dump(mode="json")
    with SessionLocal() as session:
        fee_schedule = _fee_schedule_for(session, stock, config.trade_date)
    payload["option_buy_fee"] = (
        float(fee_schedule.buy_rate) if config.option_buy_fee is None else config.option_buy_fee
    )
    payload["option_sell_fee"] = (
        float(fee_schedule.sell_rate) if config.option_sell_fee is None else config.option_sell_fee
    )
    if fee_schedule.settlement_cost_per_contract is not None and not config.settlement_cost_per_contract:
        payload["settlement_cost_per_contract"] = float(fee_schedule.settlement_cost_per_contract)
    payload["fee_schedule_id"] = str(fee_schedule.fee_schedule_id)
    row: dict[str, Any] = {
        **payload, **{f"{leg}_instrument_code": item.instrument_code for leg, item in legs.items()},
        "multiplier": convention.multiplier, "tick_size": convention.tick_size,
        "pricing_convention_version": (convention.updated_at or convention.approved_at).isoformat(),
        "calculation_version": BOX_CALCULATION_VERSION,
    }
    row["config_json"] = json.dumps(payload)
    operation, task = enqueue_task(
        run_box_spread_analysis, args=[run_id], family="box_spread", run_type="box_spread.analysis",
        target=config.underlying_instrument_code, config=row, start_date=config.trade_date,
        end_date=config.trade_date, progress_total=total, run_id=run_id,
        created_by=request.session.get("user") or "admin",
    )
    return {"run_id": str(operation.run_id), "task_id": task.id, "status": "queued"}


@router.post("/api/v1/box-calculator/calculate")
async def calculate_box(request: Request, config: BoxCalculatorRequest):
    await _require_admin(request)
    stock, convention, legs, fee_schedule = _calculator_metadata(config)
    snapshot_at = datetime.combine(config.trade_date, config.snapshot_time, TEHRAN)
    expiry_at = datetime.combine(config.expiry_date, time(12, 30), TEHRAN)
    client = await get_async_client()
    result = await client.query(
        "SELECT instrument_code, trade_time, depth_level, bid_price, bid_volume, bid_order_count, "
        "ask_price, ask_volume, ask_order_count FROM option_order_book FINAL "
        "WHERE instrument_code IN {codes:Array(String)} AND trade_date = {day:Date} "
        "AND depth_level <= 5 AND trade_time <= {cutoff:UInt32} "
        "ORDER BY instrument_code, trade_time, depth_level",
        parameters={
            "codes": [item.instrument_code for item in legs.values()],
            "day": config.trade_date, "cutoff": hhmmss(config.snapshot_time),
        },
    )
    latest: dict[str, dict[int, tuple[int, DepthLevel]]] = defaultdict(dict)
    for code, event_time, level, bid, bid_volume, bid_orders, ask, ask_volume, ask_orders in result.result_rows:
        latest[str(code)][int(level)] = (int(event_time), DepthLevel(
            int(level), float(bid), int(bid_volume), int(bid_orders),
            float(ask), int(ask_volume), int(ask_orders),
        ))
    books: dict[str, DepthBook | None] = {}
    market_data: dict[str, Any] = {}
    quality_reasons: list[str] = []
    level_one_times: list[datetime] = []
    for leg, instrument in legs.items():
        level_rows = latest.get(instrument.instrument_code, {})
        level_one = level_rows.get(1)
        book = None
        if level_one is not None:
            source_time = datetime.combine(config.trade_date, time_from_hhmmss(level_one[0]), TEHRAN)
            level_one_times.append(source_time)
            book = DepthBook(source_time, tuple(row[1] for _, row in sorted(level_rows.items())))
            quality_reasons.extend(book.validation_reasons(leg))
            if (snapshot_at - source_time).total_seconds() > config.max_quote_age_seconds:
                quality_reasons.append(f"stale_{leg}_book")
        else:
            quality_reasons.append(f"missing_{leg}_book")
        books[leg] = book
        levels = []
        for _, (event_time, depth) in sorted(level_rows.items()):
            source_time = datetime.combine(config.trade_date, time_from_hhmmss(event_time), TEHRAN)
            levels.append({
                "level": depth.level, "source_time": source_time,
                "age_seconds": max(0, int((snapshot_at - source_time).total_seconds())),
                "bid_price": depth.bid_price, "bid_volume": depth.bid_volume,
                "bid_order_count": depth.bid_order_count, "ask_price": depth.ask_price,
                "ask_volume": depth.ask_volume, "ask_order_count": depth.ask_order_count,
            })
        market_data[leg] = {
            "instrument_code": instrument.instrument_code,
            "source_time": book.source_time if book is not None else None,
            "age_seconds": max(0, int((snapshot_at - book.source_time).total_seconds())) if book is not None else None,
            "levels": levels,
        }
    cross_leg_skew = None
    if len(level_one_times) == 4:
        cross_leg_skew = int((max(level_one_times) - min(level_one_times)).total_seconds())
        if cross_leg_skew > config.max_cross_leg_skew_seconds:
            quality_reasons.append("cross_leg_quote_skew")
    if expiry_at <= snapshot_at:
        quality_reasons.append("option_expired")
    quality_reasons = list(dict.fromkeys(quality_reasons))
    settlement_cost = (
        float(fee_schedule.settlement_cost_per_contract)
        if fee_schedule.settlement_cost_per_contract is not None else None
    )
    routes = calculate_maker_routes(
        books=books, direction=config.direction, lower_strike=config.lower_strike,
        upper_strike=config.upper_strike, box_count=config.box_count,
        multiplier=convention.multiplier, buy_fee=float(fee_schedule.buy_rate),
        sell_fee=float(fee_schedule.sell_rate),
        settlement_cost_per_contract=settlement_cost, tick_size=convention.tick_size,
        snapshot_at=snapshot_at, expiry_at=expiry_at,
        market_data_valid=not quality_reasons, quality_reasons=quality_reasons,
    )
    warnings = [] if settlement_cost is not None else [
        "Settlement cost is unknown; profit is shown pre-settlement."
    ]
    selected_actions = actions(config.direction)
    return {
        "selection": {
            **config.model_dump(mode="json"), "snapshot_at": snapshot_at,
            "expiry_at": expiry_at, "expiry_cutoff": "12:30:00",
            "box_width": config.upper_strike - config.lower_strike,
        },
        "contracts": {leg: {
            "instrument_code": item.instrument_code, "symbol": item.symbol,
            "option_type": _side(item), "strike": float(item.strike_price),
            "action": selected_actions[leg],
        } for leg, item in legs.items()},
        "convention": {
            "id": str(convention.convention_id), "name": convention.name,
            "multiplier": convention.multiplier, "tick_size": convention.tick_size,
            "exercise_style": convention.exercise_style, "price_unit": convention.price_unit,
        },
        "fee_schedule": {
            "id": str(fee_schedule.fee_schedule_id), "market": _fee_market(stock),
            "effective_from": fee_schedule.effective_from,
            "effective_to": fee_schedule.effective_to,
            "buy_rate": float(fee_schedule.buy_rate), "sell_rate": float(fee_schedule.sell_rate),
            "settlement_cost_per_contract": settlement_cost,
            "source": fee_schedule.source, "notes": fee_schedule.notes,
        },
        "market_data": {
            "quality_status": "execution_grade" if not quality_reasons else "indicative",
            "quality_reasons": quality_reasons,
            "max_quote_age_seconds": config.max_quote_age_seconds,
            "max_cross_leg_skew_seconds": config.max_cross_leg_skew_seconds,
            "cross_leg_skew_seconds": cross_leg_skew,
            "legs": market_data,
        },
        "routes": routes,
        "best_route": next((route for route in routes if route["execution_grade"]), None),
        "warnings": warnings,
    }


def _checked_run(request: Request, run_id: uuid.UUID) -> dict[str, Any]:
    row = get_run(str(run_id))
    if row is None or row.family != "box_spread":
        raise HTTPException(status_code=404, detail="Box-spread run not found")
    return run_to_dict(row)


@router.get("/api/v1/box-spread/runs")
async def box_runs(request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    await _require_admin(request)
    _, rows = list_runs(family="box_spread", limit=limit, offset=offset)
    return {"items": [run_to_dict(row) for row in rows], "limit": limit, "offset": offset}


@router.get("/api/v1/box-spread/runs/{run_id}")
async def box_run(request: Request, run_id: uuid.UUID):
    await _require_admin(request)
    return _checked_run(request, run_id)


@router.get("/api/v1/box-spread/runs/{run_id}/snapshots")
async def box_snapshots(request: Request, run_id: uuid.UUID, limit: int = Query(50000, ge=1, le=200000)):
    await _require_admin(request); _checked_run(request, run_id)
    return {"items": await get_snapshots(str(run_id), limit)}


@router.get("/api/v1/box-spread/runs/{run_id}/pricings")
async def box_pricings(request: Request, run_id: uuid.UUID, limit: int = Query(50000, ge=1, le=200000)):
    await _require_admin(request); _checked_run(request, run_id)
    return {"items": await get_pricings(str(run_id), limit)}


@router.get("/api/v1/box-spread/runs/{run_id}/export.csv")
async def box_export(request: Request, run_id: uuid.UUID):
    await _require_admin(request); run = _checked_run(request, run_id)
    rows = await get_pricings(str(run_id), 200000)
    buffer = io.StringIO()
    fields = list(rows[0]) if rows else ["run_id", "snapshot_time", "classification"]
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader(); writer.writerows(rows)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="box-spread-{run_id}-{run["trade_date"]}.csv"'
    })
