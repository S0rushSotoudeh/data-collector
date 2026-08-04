from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.analytics.iv import (
    MODEL_VERSION, black76_vega, fit_orc_wing, implied_volatility, orc_wing,
    parity_forward_bounds, point_weight, robust_forward,
)
from src.analytics.iv_config import IVSurfaceRunConfig
from src.analytics.parity_engine import aligned_snapshots, hhmmss, latest_state_rows, ns_yield, time_from_hhmmss
from src.db.clickhouse import get_client
from src.db.clickhouse.iv_surface import FIT_COLUMNS, POINT_COLUMNS, insert_fits, insert_points
from src.db.models.operations import OptionPricingConvention
from src.db.models.option import OptionInstrument
from src.db.session import SessionLocal
from src.services.operation_runs import fail_run as fail_operation_run
from src.services.operation_runs import get_run, run_to_dict, update_progress, update_run

TEHRAN = ZoneInfo("Asia/Tehran")


def _run_row(client, run_id: str) -> dict[str, Any]:
    operation = get_run(run_id)
    if operation is None or operation.family != "iv_orc":
        raise ValueError("unknown IV surface run")
    return run_to_dict(operation)


def _update_run(client, stored: dict[str, Any], status: str, **values: Any) -> dict[str, Any]:
    updated = dict(stored)
    updated.update(values, status=status, updated_at=datetime.now(TEHRAN))
    result = {key: updated.get(key, 0) for key in (
        "completed_snapshot_count", "point_count", "fit_count", "warning_count", "quality_summary"
    )}
    if status == "running":
        update_progress(
            updated["run_id"], current=int(updated.get("completed_snapshot_count", 0) or 0),
            output_count=int(updated.get("point_count", 0) or 0),
            warning_count=int(updated.get("warning_count", 0) or 0), result=result,
        )
    else:
        update_run(
            updated["run_id"], status=status, result=result,
            progress_current=int(updated.get("completed_snapshot_count", 0) or 0),
            output_count=int(updated.get("point_count", 0) or 0),
            warning_count=int(updated.get("warning_count", 0) or 0),
            error=str(updated.get("error") or ""),
        )
    return updated


def _load_inputs(config: IVSurfaceRunConfig) -> tuple[OptionPricingConvention, list[OptionInstrument]]:
    with SessionLocal() as session:
        convention = session.get(OptionPricingConvention, config.pricing_convention_id)
        options = session.execute(
            select(OptionInstrument).where(
                OptionInstrument.underlying_instrument_code == config.underlying_instrument_code,
                OptionInstrument.expiry_date >= config.start_date,
            )
        ).scalars().all()
    if convention is None or not convention.approved or convention.approved_at is None:
        raise ValueError("pricing_convention_not_approved")
    if not convention.black76_compatible or convention.exercise_style.lower() not in {"european", "european-style"}:
        raise ValueError("pricing_convention_not_black76_compatible")
    usable = [item for item in options if item.strike_price and item.expiry_date and (item.option_type or "").lower() in {"call", "c", "put", "p"}]
    if not usable:
        raise ValueError("no_mapped_option_instruments")
    return convention, usable


def _quotes(client, codes: list[str], day: date, end: time) -> dict[str, list[tuple]]:
    result = client.query(
        "SELECT instrument_code, trade_time, bid_price, ask_price, bid_volume, ask_volume "
        "FROM option_order_book FINAL WHERE instrument_code IN {codes:Array(String)} AND trade_date = {day:Date} "
        "AND depth_level = 1 AND trade_time <= {end:UInt32} ORDER BY instrument_code, trade_time, ingested_at",
        parameters={"codes": codes, "day": day, "end": hhmmss(end)},
    )
    grouped: dict[str, list[tuple]] = defaultdict(list)
    for code, *fields in result.result_rows:
        grouped[code].append(tuple(fields))
    return grouped


def _curve_rows(client, day: date, end: time) -> list[tuple]:
    return client.query(
        "SELECT trade_time, beta0, beta1, beta2, lambda, rmse, n_bonds, converged "
        "FROM yield_curve_fits FINAL WHERE trade_date = {day:Date} AND curve_side = 'ask' "
        "AND trade_time <= {end:UInt32} ORDER BY trade_time",
        parameters={"day": day, "end": hhmmss(end)},
    ).result_rows


def _rate(curves: list[tuple], snapshot: datetime, ttm: float, manual: float | None) -> tuple[float | None, str]:
    cutoff = hhmmss(snapshot.timetz().replace(tzinfo=None))
    curve = None
    for row in curves:
        if int(row[0]) > cutoff:
            break
        curve = row
    if curve and bool(curve[7]) and int(curve[6]) >= 4 and all(value is not None for value in curve[1:5]):
        return float(ns_yield(ttm, *map(float, curve[1:5]))), "bond_curve"
    if manual is not None:
        return manual, "manual_fallback"
    return None, "missing"


def _quote(raw: tuple | None, snapshot: datetime, max_age: int) -> dict[str, Any] | None:
    if raw is None:
        return None
    quote_time = datetime.combine(snapshot.date(), time_from_hhmmss(int(raw[0])), TEHRAN)
    age = max(0, int((snapshot - quote_time).total_seconds()))
    if age > max_age:
        return {"rejection": "stale_quote", "quote_time": quote_time, "age": age, "raw": raw}
    if raw[1] <= 0 or raw[2] <= 0 or raw[1] > raw[2]:
        return {"rejection": "crossed_or_one_sided_quote", "quote_time": quote_time, "age": age, "raw": raw}
    return {"rejection": "", "quote_time": quote_time, "age": age, "raw": raw}


def _price_factor(convention: OptionPricingConvention) -> float:
    unit = convention.price_unit.strip().lower()
    return 10.0 if unit in {"toman", "tomans"} else 1.0


def process_run(run_id: str) -> dict[str, int]:
    client = get_client()
    stored = _run_row(client, run_id)
    if stored["model_version"] != MODEL_VERSION:
        raise RuntimeError("unsupported IV model version")
    config = IVSurfaceRunConfig.model_validate_json(stored["config_json"])
    convention, instruments = _load_inputs(config)
    stored = _update_run(client, stored, "running", error="")
    codes = [item.instrument_code for item in instruments]
    metadata = {item.instrument_code: item for item in instruments}
    pairs: dict[tuple[date, float], dict[str, str]] = defaultdict(dict)
    for item in instruments:
        side = "call" if (item.option_type or "").lower() in {"call", "c"} else "put"
        pairs[(item.expiry_date, float(item.strike_price))][side] = item.instrument_code
    counts = {"completed_snapshot_count": 0, "point_count": 0, "fit_count": 0, "warning_count": 0}
    price_factor = _price_factor(convention)
    day = config.start_date
    while day <= config.end_date:
        snapshots = aligned_snapshots(day, config.session_start, config.session_end, config.interval_seconds)
        grouped = _quotes(client, codes, day, config.session_end)
        states = {code: latest_state_rows(grouped.get(code, []), snapshots) for code in codes}
        curves = _curve_rows(client, day, config.session_end)
        points_batch: list[dict[str, Any]] = []
        fits_batch: list[dict[str, Any]] = []
        for snapshot_index, snapshot in enumerate(snapshots):
            snapshot_quotes = {
                code: _quote(states[code][snapshot_index], snapshot, config.max_quote_age_seconds) for code in codes
            }
            expiry_forwards: dict[date, tuple[float, float, float, float, str]] = {}
            for expiry in sorted({item.expiry_date for item in instruments}):
                expiry_at = datetime.combine(expiry, config.session_end, TEHRAN)
                ttm = (expiry_at - snapshot).total_seconds() / (365.25 * 86400)
                if ttm <= 0:
                    continue
                rate, rate_source = _rate(curves, snapshot, ttm, config.manual_funding_rate)
                if rate is None:
                    continue
                intervals = []
                for (pair_expiry, strike), pair in pairs.items():
                    if pair_expiry != expiry or set(pair) != {"call", "put"}:
                        continue
                    call, put = snapshot_quotes[pair["call"]], snapshot_quotes[pair["put"]]
                    if not call or not put or call["rejection"] or put["rejection"]:
                        continue
                    cr, pr = call["raw"], put["raw"]
                    try:
                        lo, hi = parity_forward_bounds(strike, rate, ttm, cr[1] * price_factor, cr[2] * price_factor, pr[1] * price_factor, pr[2] * price_factor)
                    except ValueError:
                        continue
                    depth = min(cr[3], cr[4], pr[3], pr[4])
                    intervals.append((lo, hi, math.log1p(depth)))
                if intervals:
                    lo, hi, forward = robust_forward(intervals)
                    expiry_forwards[expiry] = (lo, hi, forward, rate, rate_source)

            valid_by_fit: dict[tuple[date, str], list[dict[str, Any]]] = defaultdict(list)
            now = datetime.now(TEHRAN)
            for code, item in metadata.items():
                quote = snapshot_quotes[code]
                expiry = item.expiry_date
                strike = float(item.strike_price)
                option_type = "call" if (item.option_type or "").lower() in {"call", "c"} else "put"
                forward_info = expiry_forwards.get(expiry)
                expiry_at = datetime.combine(expiry, config.session_end, TEHRAN)
                point_ttm = max(0.0, (expiry_at - snapshot).total_seconds() / (365.25 * 86400))
                for side, raw_index, depth_index in (("bid", 1, 3), ("ask", 2, 4)):
                    rejection = "" if quote else "missing_quote"
                    if quote and quote["rejection"]:
                        rejection = quote["rejection"]
                    price = quote["raw"][raw_index] * price_factor if quote else None
                    row: dict[str, Any] = {
                        "run_id": run_id, "snapshot_time": snapshot, "trade_date": day,
                        "underlying_instrument_code": config.underlying_instrument_code, "instrument_code": code,
                        "option_type": option_type, "side": side, "strike": strike, "expiry_date": expiry,
                        "ttm_years": point_ttm, "forward_lower": None, "forward_upper": None, "forward": None,
                        "rate": None, "rate_source": "missing", "price": price, "iv": None, "vega": None,
                        "depth": int(quote["raw"][depth_index]) if quote else 0,
                        "quote_time": quote["quote_time"] if quote else None,
                        "quote_age_seconds": quote["age"] if quote else None, "weight": None,
                        "rejection_reason": rejection, "created_at": now,
                    }
                    if not rejection and not forward_info:
                        row["rejection_reason"] = "missing_forward_or_rate"
                    elif not rejection:
                        lo, hi, forward, rate, rate_source = forward_info
                        expiry_at = datetime.combine(expiry, config.session_end, TEHRAN)
                        ttm = (expiry_at - snapshot).total_seconds() / (365.25 * 86400)
                        row.update(ttm_years=ttm, forward_lower=lo, forward_upper=hi, forward=forward, rate=rate, rate_source=rate_source)
                        # Use the OTM contract at each strike to avoid duplicate call/put observations.
                        if (strike < forward and option_type != "put") or (strike >= forward and option_type != "call"):
                            row["rejection_reason"] = "non_otm_contract"
                        else:
                            try:
                                iv = implied_volatility(float(price), forward, strike, rate, ttm, option_type)
                                vega = black76_vega(forward, strike, rate, ttm, iv)
                                weight = point_weight(vega, row["depth"], row["quote_age_seconds"], config.max_quote_age_seconds)
                                row.update(iv=iv, vega=vega, weight=weight)
                                valid_by_fit[(expiry, side)].append(row)
                            except ValueError as exc:
                                row["rejection_reason"] = str(exc)
                    points_batch.append(row)

            fitted: dict[tuple[date, str], dict[str, Any]] = {}
            for (expiry, side), rows in valid_by_fit.items():
                flags: list[str] = []
                try:
                    params, rmse, converged = fit_orc_wing(
                        [math.log(row["strike"] / row["forward"]) for row in rows],
                        [row["iv"] for row in rows], [row["weight"] for row in rows],
                    )
                except ValueError as exc:
                    params, rmse, converged = None, None, False
                    flags.append(str(exc))
                fit = {
                    "run_id": run_id, "snapshot_time": snapshot, "trade_date": day,
                    "underlying_instrument_code": config.underlying_instrument_code, "expiry_date": expiry,
                    "side": side, "forward": rows[0]["forward"], "ttm_years": rows[0]["ttm_years"],
                    **{name: getattr(params, name) if params else None for name in ("vc", "sc", "pc", "cc", "dc", "uc")},
                    "dsm": 0.5, "usm": 0.5, "rmse": rmse, "point_count": len(rows),
                    "converged": int(converged), "quality_flags": flags, "created_at": now,
                }
                fitted[(expiry, side)] = fit
                fits_batch.append(fit)
            for expiry in {key[0] for key in fitted}:
                bid, ask = fitted.get((expiry, "bid")), fitted.get((expiry, "ask"))
                if bid and ask and bid["converged"] and ask["converged"]:
                    from src.analytics.iv import WingParameters
                    bp = WingParameters(**{name: bid[name] for name in ("vc", "sc", "pc", "cc", "dc", "uc")})
                    ap = WingParameters(**{name: ask[name] for name in ("vc", "sc", "pc", "cc", "dc", "uc")})
                    xs = [i / 100 for i in range(-100, 101)]
                    if any(orc_wing(x, bp) > orc_wing(x, ap) for x in xs):
                        bid["quality_flags"].append("fitted_bid_above_ask")
                        ask["quality_flags"].append("fitted_bid_above_ask")
                        counts["warning_count"] += 1
            counts["completed_snapshot_count"] += 1
        insert_points(points_batch, client)
        insert_fits(fits_batch, client)
        counts["point_count"] += len(points_batch)
        counts["fit_count"] += sum(int(row["converged"]) for row in fits_batch)
        stored = _update_run(client, stored, "running", **counts)
        day += timedelta(days=1)
    _update_run(client, stored, "completed", quality_summary=json.dumps(counts), error="", **counts)
    return counts


def fail_run(run_id: str, error: str) -> None:
    fail_operation_run(run_id, error)
