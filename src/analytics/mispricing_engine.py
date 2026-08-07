from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from src.analytics.iv import (
    MAX_IV, MIN_IV, WingParameters, black76_price, black76_vega,
    fit_orc_wing_robust, implied_volatility, orc_wing,
    parity_forward_bounds, point_weight, robust_forward,
)
from src.analytics.mispricing_config import OptionMispricingRunConfig
from src.analytics.parity_engine import aligned_snapshots, hhmmss, latest_state_rows, ns_yield, time_from_hhmmss
from src.db.clickhouse import get_client
from src.db.clickhouse.mispricing import (
    get_frozen_universe, insert_fits, insert_observations, insert_rankings,
)
from src.services.operation_runs import RunProgressReporter, fail_run as fail_operation_run
from src.services.operation_runs import get_run, run_to_dict, update_run

TEHRAN = ZoneInfo("Asia/Tehran")
MODEL_VERSION = "option-mispricing-orc-v1"
CONFIGURATION_VERSION = "option-mispricing-config-v1"


def _run_row(run_id: str) -> dict[str, Any]:
    operation = get_run(run_id)
    if operation is None or operation.family != "option_mispricing":
        raise ValueError("unknown option mispricing run")
    return run_to_dict(operation)


def _quotes(client, codes: list[str], day: date, end: time) -> dict[str, list[tuple]]:
    result = client.query(
        "SELECT instrument_code, trade_time, bid_price, ask_price, bid_volume, ask_volume "
        "FROM option_order_book FINAL WHERE instrument_code IN {codes:Array(String)} "
        "AND trade_date = {day:Date} AND depth_level = 1 AND trade_time <= {end:UInt32} "
        "ORDER BY instrument_code, trade_time, ingested_at",
        parameters={"codes": codes, "day": day, "end": hhmmss(end)},
    )
    grouped: dict[str, list[tuple]] = defaultdict(list)
    for code, *fields in result.result_rows:
        grouped[str(code)].append(tuple(fields))
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


def _quote(raw: tuple | None, snapshot: datetime, max_age: int) -> dict[str, Any]:
    if raw is None:
        return {"rejection": "missing_quote", "raw": None, "quote_time": None, "age": None}
    quote_time = datetime.combine(snapshot.date(), time_from_hhmmss(int(raw[0])), TEHRAN)
    age = max(0, int((snapshot - quote_time).total_seconds()))
    if age > max_age:
        rejection = "stale_quote"
    elif float(raw[1]) <= 0 or float(raw[2]) <= 0:
        rejection = "one_sided_quote"
    elif float(raw[1]) > float(raw[2]):
        rejection = "crossed_quote"
    else:
        rejection = ""
    return {"rejection": rejection, "raw": raw, "quote_time": quote_time, "age": age}


def _fit_expiry(
    *, run_id: str, snapshot: datetime, underlying: str, expiry: date,
    contracts: list[dict[str, Any]], quotes: dict[str, dict[str, Any]], curves: list[tuple],
    config: OptionMispricingRunConfig, price_factor: float, now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expiry_at = datetime.combine(expiry, config.expiry_cutoff, TEHRAN)
    ttm = (expiry_at - snapshot).total_seconds() / (365.25 * 86400)
    flags: list[str] = []
    rate, rate_source = _rate(curves, snapshot, max(ttm, 0.0), config.manual_funding_rate)
    if rate_source == "manual_fallback":
        flags.append("manual_funding_rate_fallback")
    pairs: dict[float, dict[str, dict[str, Any]]] = defaultdict(dict)
    for contract in contracts:
        pairs[float(contract["strike"])].setdefault(str(contract["option_type"]), contract)
    intervals: list[tuple[float, float, float]] = []
    if ttm > 0 and rate is not None:
        for strike, pair in pairs.items():
            if not {"call", "put"}.issubset(pair):
                continue
            call_quote = quotes[pair["call"]["instrument_code"]]
            put_quote = quotes[pair["put"]["instrument_code"]]
            if call_quote["rejection"] or put_quote["rejection"]:
                continue
            call_raw, put_raw = call_quote["raw"], put_quote["raw"]
            try:
                lower, upper = parity_forward_bounds(
                    strike, rate, ttm,
                    float(call_raw[1]) * price_factor, float(call_raw[2]) * price_factor,
                    float(put_raw[1]) * price_factor, float(put_raw[2]) * price_factor,
                )
            except ValueError:
                continue
            depth = min(int(call_raw[3]), int(call_raw[4]), int(put_raw[3]), int(put_raw[4]))
            intervals.append((lower, upper, math.log1p(max(depth, 0))))
    forward_lower = forward_upper = forward = None
    if ttm <= 0:
        flags.append("expired")
    elif rate is None:
        flags.append("missing_rate")
    elif not intervals:
        flags.append("missing_executable_parity_forward")
    else:
        forward_lower, forward_upper, forward = robust_forward(intervals)

    candidates: list[dict[str, Any]] = []
    if forward is not None and rate is not None:
        for strike, pair in sorted(pairs.items()):
            wanted = "put" if strike < forward else "call"
            contract = pair.get(wanted)
            if contract is None:
                continue
            quote = quotes[contract["instrument_code"]]
            if quote["rejection"]:
                continue
            raw = quote["raw"]
            midpoint = (float(raw[1]) + float(raw[2])) * 0.5 * price_factor
            try:
                iv = implied_volatility(midpoint, forward, strike, rate, ttm, wanted)
                vega = black76_vega(forward, strike, rate, ttm, iv)
            except ValueError:
                continue
            depth = min(int(raw[3]), int(raw[4]))
            candidates.append({
                "instrument_code": contract["instrument_code"], "strike": strike,
                "x": math.log(strike / forward), "iv": iv,
                "weight": point_weight(vega, depth, int(quote["age"]), config.max_quote_age_seconds),
            })

    robust = None
    excluded_codes: list[str] = []
    if forward is not None and rate is not None:
        try:
            robust = fit_orc_wing_robust(
                [row["x"] for row in candidates], [row["iv"] for row in candidates],
                [row["weight"] for row in candidates], mad_limit=3.5, max_passes=3,
            )
            excluded_codes = [candidates[index]["instrument_code"] for index in robust.excluded_indices]
            if excluded_codes:
                flags.append("reference_outliers_excluded")
            if not robust.converged:
                flags.append("fit_not_converged")
        except ValueError as exc:
            flags.append(str(exc))
    converged = bool(robust and robust.converged)
    params: WingParameters | None = robust.parameters if robust else None
    fit = {
        "run_id": run_id, "trade_date": snapshot.date(), "snapshot_time": snapshot,
        "underlying_instrument_code": underlying, "expiry_date": expiry,
        "forward_lower": forward_lower, "forward_upper": forward_upper, "forward": forward,
        "rate": rate, "rate_source": rate_source, "ttm_years": max(ttm, 0.0),
        **{name: getattr(params, name) if params else None for name in ("vc", "sc", "pc", "cc", "dc", "uc")},
        "dsm": params.dsm if params else 0.5, "usm": params.usm if params else 0.5,
        "rmse": robust.rmse if robust else None, "point_count": len(candidates),
        "used_point_count": len(robust.kept_indices) if robust else 0,
        "excluded_point_count": len(excluded_codes), "fit_passes": robust.passes if robust else 0,
        "converged": int(converged), "excluded_instrument_codes": excluded_codes,
        "excluded_reasons": ["mad_outlier"] * len(excluded_codes),
        "quality_status": "warning" if converged and flags else "valid" if converged else "invalid",
        "quality_flags": sorted(set(flags)), "created_at": now,
    }
    return fit, {"parameters": params if converged else None, "excluded_codes": set(excluded_codes)}


def _observation(
    *, run_id: str, snapshot: datetime, contract: dict[str, Any], quote: dict[str, Any],
    fit: dict[str, Any], fit_state: dict[str, Any], price_factor: float, now: datetime,
) -> dict[str, Any]:
    raw = quote["raw"]
    bid = float(raw[1]) * price_factor if raw else None
    ask = float(raw[2]) * price_factor if raw else None
    midpoint = (bid + ask) / 2 if raw else None
    fair_iv = fair_price = None
    params = fit_state["parameters"]
    rejection = quote["rejection"]
    if params is None:
        rejection = rejection or "reference_fit_failed"
    else:
        fair_iv = orc_wing(math.log(float(contract["strike"]) / float(fit["forward"])), params)
        if not MIN_IV <= fair_iv <= MAX_IV:
            rejection = rejection or "fair_iv_outside_supported_range"
            fair_iv = None
        else:
            fair_price = black76_price(
                float(fit["forward"]), float(contract["strike"]), float(fit["rate"]),
                float(fit["ttm_years"]), fair_iv, str(contract["option_type"]),
            )
    warning = contract["instrument_code"] in fit_state["excluded_codes"]
    if warning and not rejection:
        rejection = "reference_fit_outlier"
    quality = "invalid" if quote["rejection"] or fair_price is None else "warning" if warning or fit["quality_status"] == "warning" else "valid"
    # Invalid observations retain raw bid/fair/ask values for diagnostics, but
    # must not retain residuals that could be mistaken for mispricing.
    def distance(value: float | None) -> float | None:
        return value - fair_price if quality != "invalid" and value is not None and fair_price is not None else None
    bid_distance, ask_distance, midpoint_distance = distance(bid), distance(ask), distance(midpoint)
    def bps(value: float | None) -> float | None:
        return value / fair_price * 10_000 if value is not None and fair_price and fair_price > 0 else None
    return {
        "run_id": run_id, "trade_date": snapshot.date(), "snapshot_time": snapshot,
        "underlying_instrument_code": contract["underlying_instrument_code"],
        "instrument_code": contract["instrument_code"], "option_type": contract["option_type"],
        "strike": float(contract["strike"]), "expiry_date": contract["expiry_date"],
        "bid_price": bid, "midpoint_price": midpoint, "fair_price": fair_price, "ask_price": ask,
        "fair_iv": fair_iv, "bid_distance": bid_distance, "ask_distance": ask_distance,
        "midpoint_distance": midpoint_distance, "bid_distance_bps": bps(bid_distance),
        "ask_distance_bps": bps(ask_distance), "midpoint_distance_bps": bps(midpoint_distance),
        "forward": fit["forward"], "rate": fit["rate"], "rate_source": fit["rate_source"],
        "depth": min(int(raw[3]), int(raw[4])) if raw else 0,
        "bid_depth": int(raw[3]) if raw else 0, "ask_depth": int(raw[4]) if raw else 0,
        "quote_time": quote["quote_time"], "quote_age_seconds": quote["age"],
        "fit_rmse": fit["rmse"], "quality_status": quality, "rejection_reason": rejection,
        "created_at": now,
    }


def _ranking_rows(
    run_id: str, trade_date: date, underlyings: set[str], snapshots: list[datetime],
    stats: dict[str, dict[str, Any]], universe_warnings: dict[str, set[str]], now: datetime,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for underlying in sorted(underlyings):
        values = stats[underlying]
        mid = values["midpoint"]
        absolute = [abs(value) for value in mid]
        total = len(mid)
        def threshold(level: float) -> tuple[int, float]:
            count = sum(value >= level for value in absolute)
            return count, count / total if total else 0.0
        outside25, share25 = threshold(25); outside50, share50 = threshold(50); outside100, share100 = threshold(100)
        warnings = set(universe_warnings[underlying]) | values["warnings"]
        output.append({
            "run_id": run_id, "trade_date": trade_date, "underlying_instrument_code": underlying,
            "valid_contract_count": len(values["contracts"]), "valid_expiry_count": len(values["expiries"]),
            "valid_snapshot_count": len(values["snapshots"]), "total_snapshot_count": len(snapshots),
            "snapshot_coverage": len(values["snapshots"]) / len(snapshots) if snapshots else 0.0,
            "median_abs_midpoint_bps": float(np.quantile(absolute, .5)) if absolute else None,
            "p90_abs_midpoint_bps": float(np.quantile(absolute, .9)) if absolute else None,
            "largest_bid_deviation_bps": max(values["bid"], key=abs) if values["bid"] else None,
            "largest_ask_deviation_bps": max(values["ask"], key=abs) if values["ask"] else None,
            "outside_25_count": outside25, "outside_25_share": share25,
            "outside_50_count": outside50, "outside_50_share": share50,
            "outside_100_count": outside100, "outside_100_share": share100,
            "affected_contract_count": len(values["affected_contracts"]),
            "excluded_observation_count": values["excluded"],
            "quality_warnings": sorted(warnings), "created_at": now,
        })
    return output


def process_run(run_id: str) -> dict[str, int]:
    client = get_client()
    stored = _run_row(run_id)
    if stored.get("model_version") != MODEL_VERSION or stored.get("configuration_version") != CONFIGURATION_VERSION:
        raise RuntimeError("unsupported option mispricing model or configuration version")
    config = OptionMispricingRunConfig.model_validate(stored["run_config"])
    universe = get_frozen_universe(run_id, client)
    if not universe:
        raise ValueError("empty_frozen_universe")
    snapshots = aligned_snapshots(config.trade_date, config.start_time, config.end_time, config.interval_seconds)
    all_underlyings = {str(row["underlying_instrument_code"]) for row in universe if row["underlying_instrument_code"]}
    progress = RunProgressReporter(run_id)
    progress.set_total(len(snapshots) * len(all_underlyings))
    update_run(run_id, status="running", error="")
    codes = [str(row["instrument_code"]) for row in universe]
    grouped_quotes = _quotes(client, codes, config.trade_date, config.end_time)
    states = {code: latest_state_rows(grouped_quotes.get(code, []), snapshots) for code in codes}
    curves = _curve_rows(client, config.trade_date, config.end_time)
    eligible_groups: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
    universe_warnings: dict[str, set[str]] = defaultdict(set)
    for row in universe:
        underlying = str(row["underlying_instrument_code"] or "")
        universe_warnings[underlying].update(row.get("eligibility_reasons") or [])
        if row.get("eligible") and underlying and row.get("expiry_date") is not None:
            eligible_groups[(underlying, row["expiry_date"])].append(row)
    by_underlying: dict[str, list[tuple[date, list[dict[str, Any]]]]] = defaultdict(list)
    for (underlying, expiry), rows in eligible_groups.items():
        by_underlying[underlying].append((expiry, rows))
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "midpoint": [], "bid": [], "ask": [], "contracts": set(), "expiries": set(),
        "snapshots": set(), "affected_contracts": set(), "excluded": 0, "warnings": set(),
    })
    counts = {"snapshot_count": 0, "fit_count": 0, "observation_count": 0, "valid_observation_count": 0, "warning_count": 0}
    price_factor = float(stored.get("price_factor", 1.0))
    completed = 0
    for snapshot_index, snapshot in enumerate(snapshots):
        snapshot_quotes = {code: _quote(states[code][snapshot_index], snapshot, config.max_quote_age_seconds) for code in codes}
        fit_rows: list[dict[str, Any]] = []
        observation_rows: list[dict[str, Any]] = []
        now = datetime.now(TEHRAN)
        for underlying in sorted(all_underlyings):
            for expiry, contracts in sorted(by_underlying.get(underlying, []), key=lambda value: value[0]):
                fit, fit_state = _fit_expiry(
                    run_id=run_id, snapshot=snapshot, underlying=underlying, expiry=expiry,
                    contracts=contracts, quotes=snapshot_quotes, curves=curves, config=config,
                    price_factor=price_factor, now=now,
                )
                fit_rows.append(fit)
                counts["fit_count"] += int(fit["converged"])
                stats[underlying]["warnings"].update(fit["quality_flags"])
                counts["warning_count"] += int(fit["quality_status"] == "warning")
                for contract in contracts:
                    row = _observation(
                        run_id=run_id, snapshot=snapshot, contract=contract,
                        quote=snapshot_quotes[contract["instrument_code"]], fit=fit,
                        fit_state=fit_state, price_factor=price_factor, now=now,
                    )
                    observation_rows.append(row)
                    counts["observation_count"] += 1
                    values = stats[underlying]
                    if row["quality_status"] in {"valid", "warning"} and row["midpoint_distance_bps"] is not None:
                        values["midpoint"].append(float(row["midpoint_distance_bps"]))
                        values["bid"].append(float(row["bid_distance_bps"]))
                        values["ask"].append(float(row["ask_distance_bps"]))
                        values["contracts"].add(row["instrument_code"]); values["expiries"].add(expiry)
                        values["snapshots"].add(snapshot)
                        if abs(float(row["midpoint_distance_bps"])) >= 25:
                            values["affected_contracts"].add(row["instrument_code"])
                        counts["valid_observation_count"] += 1
                    else:
                        values["excluded"] += 1
            completed += 1
            progress.checkpoint(
                completed, output_count=counts["observation_count"], warning_count=counts["warning_count"],
                result=counts,
            )
        insert_fits(fit_rows, client)
        insert_observations(observation_rows, client)
        counts["snapshot_count"] += 1
    rankings = _ranking_rows(run_id, config.trade_date, all_underlyings, snapshots, stats, universe_warnings, datetime.now(TEHRAN))
    insert_rankings(rankings, client)
    result = counts | {"underlying_count": len(all_underlyings), "ranking_count": len(rankings)}
    progress.checkpoint(completed, output_count=counts["observation_count"], warning_count=counts["warning_count"], result=result, force=True)
    update_run(
        run_id, status="completed", result=result, progress_current=completed,
        output_count=counts["observation_count"], warning_count=counts["warning_count"], error="",
    )
    return result


def fail_run(run_id: str, error: str) -> None:
    fail_operation_run(run_id, error)
