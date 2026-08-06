from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from src.analytics.box_spread import BOX_CALCULATION_VERSION, LEGS, price_box
from src.analytics.box_spread_config import BoxSpreadRunConfig
from src.analytics.depth import DepthBook, DepthLevel
from src.analytics.parity_engine import aligned_snapshots, hhmmss, time_from_hhmmss
from src.analytics.yield_curve import ns_yield
from src.db.clickhouse import get_client
from src.db.clickhouse.box_spread import insert_pricings, insert_snapshots
from src.services.operation_runs import RunProgressReporter, fail_run as fail_operation_run
from src.services.operation_runs import get_run, run_to_dict, update_run


TEHRAN = ZoneInfo("Asia/Tehran")


def _run_row(run_id: str) -> dict[str, Any]:
    operation = get_run(run_id)
    if operation is None or operation.family != "box_spread":
        raise ValueError("unknown box-spread run")
    return run_to_dict(operation)


def _book_events(client, codes: list[str], config: BoxSpreadRunConfig) -> dict[str, list[tuple[int, DepthLevel]]]:
    result = client.query(
        "SELECT instrument_code, trade_time, depth_level, bid_price, bid_volume, bid_order_count, "
        "ask_price, ask_volume, ask_order_count FROM option_order_book FINAL "
        "WHERE instrument_code IN {codes:Array(String)} AND trade_date = {day:Date} "
        "AND depth_level <= 5 AND trade_time <= {end:UInt32} "
        "ORDER BY instrument_code, trade_time, depth_level",
        parameters={"codes": codes, "day": config.trade_date, "end": hhmmss(config.session_end)},
    )
    events: dict[str, list[tuple[int, DepthLevel]]] = defaultdict(list)
    for code, event_time, level, bid, bid_volume, bid_orders, ask, ask_volume, ask_orders in result.result_rows:
        events[str(code)].append((int(event_time), DepthLevel(
            int(level), float(bid), int(bid_volume), int(bid_orders),
            float(ask), int(ask_volume), int(ask_orders),
        )))
    for rows in events.values():
        rows.sort(key=lambda item: (item[0], item[1].level))
    return events


def _states(events: list[tuple[int, DepthLevel]], snapshots: list[datetime]) -> list[DepthBook | None]:
    """Rebuild event-time depth by carrying each level forward independently.

    TSETMC history is an update stream, not a guarantee that every timestamp
    contains a complete five-level image.  Level one determines quote age;
    deeper levels are the latest values observed at or before the snapshot.
    """
    output: list[DepthBook | None] = []
    index = 0
    levels: dict[int, DepthLevel] = {}
    level_one_time: datetime | None = None
    for snapshot in snapshots:
        cutoff = hhmmss(snapshot.timetz().replace(tzinfo=None))
        while index < len(events) and events[index][0] <= cutoff:
            event_time, level = events[index]
            levels[level.level] = level
            if level.level == 1:
                level_one_time = datetime.combine(snapshot.date(), time_from_hhmmss(event_time), TEHRAN)
            index += 1
        output.append(
            DepthBook(level_one_time, tuple(levels[level] for level in sorted(levels)))
            if level_one_time is not None else None
        )
    return output


def _curve_rows(client, config: BoxSpreadRunConfig) -> list[tuple]:
    return client.query(
        "SELECT trade_time, beta0, beta1, beta2, lambda, rmse, n_bonds, converged "
        "FROM yield_curve_fits FINAL WHERE trade_date = {day:Date} AND curve_side = 'ask' "
        "AND trade_time <= {end:UInt32} ORDER BY trade_time",
        parameters={"day": config.trade_date, "end": hhmmss(config.session_end)},
    ).result_rows


def _benchmark(curves: list[tuple], snapshot: datetime, ttm: float, config: BoxSpreadRunConfig) -> tuple[float | None, str, tuple | None, list[str], list[str]]:
    curve = None
    cutoff = hhmmss(snapshot.timetz().replace(tzinfo=None))
    for row in curves:
        if int(row[0]) > cutoff:
            break
        curve = row
    reasons: list[str] = []
    warnings: list[str] = []
    curve_rate = None
    if curve and bool(curve[7]) and int(curve[6]) >= 4 and all(value is not None for value in curve[1:5]):
        curve_rate = float(ns_yield(ttm, *map(float, curve[1:5])))
        curve_time = datetime.combine(snapshot.date(), time_from_hhmmss(int(curve[0])), TEHRAN)
        if (snapshot - curve_time).total_seconds() > 60:
            warnings.append("akhza_curve_older_than_60_seconds")
        if curve[5] is not None and float(curve[5]) * 10_000 > 200:
            warnings.append("akhza_curve_rmse_over_200_bps")
    if config.funding_source == "manual":
        return config.manual_funding_rate, "manual", curve, reasons, warnings
    if curve_rate is not None:
        if config.funding_spread is not None:
            curve_rate += config.funding_spread
            return curve_rate, "akhza_ask_curve+spread", curve, reasons, warnings
        return curve_rate, "akhza_ask_curve", curve, reasons, warnings
    if config.funding_source == "mixed" and config.manual_funding_rate is not None:
        warnings.append("manual_funding_fallback")
        return config.manual_funding_rate, "manual_fallback", curve, reasons, warnings
    reasons.append("missing_or_invalid_akhza_curve")
    return None, "missing", curve, reasons, warnings


def _book_fields(leg: str, code: str, book: DepthBook | None, snapshot: datetime) -> dict[str, Any]:
    fields: dict[str, Any] = {f"{leg}_instrument_code": code}
    if book is None:
        fields.update({
            f"{leg}_source_time": None, f"{leg}_age_seconds": None,
            f"{leg}_best_bid": None, f"{leg}_best_ask": None,
            f"{leg}_bid_total_volume": 0, f"{leg}_ask_total_volume": 0,
            f"{leg}_bid_order_count": 0, f"{leg}_ask_order_count": 0,
        })
        return fields
    best = book.best
    fields.update({
        f"{leg}_source_time": book.source_time,
        f"{leg}_age_seconds": max(0, int((snapshot - book.source_time).total_seconds())),
        f"{leg}_best_bid": best.bid_price if best else None,
        f"{leg}_best_ask": best.ask_price if best else None,
        f"{leg}_bid_total_volume": book.total_volume("sell"),
        f"{leg}_ask_total_volume": book.total_volume("buy"),
        f"{leg}_bid_order_count": best.bid_order_count if best else 0,
        f"{leg}_ask_order_count": best.ask_order_count if best else 0,
    })
    return fields


def process_run(run_id: str) -> dict[str, int]:
    client = get_client()
    stored = _run_row(run_id)
    if stored.get("calculation_version") != BOX_CALCULATION_VERSION:
        raise RuntimeError("unsupported box-spread calculation version")
    config = BoxSpreadRunConfig.model_validate_json(stored["config_json"])
    leg_codes = {leg: str(stored[f"{leg}_instrument_code"]) for leg in LEGS}
    multiplier = int(stored["multiplier"])
    tick_size = float(stored["tick_size"])
    update_run(run_id, status="running", error="")
    snapshots = aligned_snapshots(config.trade_date, config.session_start, config.session_end, config.interval_seconds)
    events = _book_events(client, list(leg_codes.values()), config)
    states = {leg: _states(events.get(code, []), snapshots) for leg, code in leg_codes.items()}
    curves = _curve_rows(client, config)
    progress = RunProgressReporter(run_id)
    progress.set_total(len(snapshots))
    snapshot_rows: list[dict[str, Any]] = []
    pricing_rows: list[dict[str, Any]] = []
    counts = {"snapshot_count": 0, "valid_count": 0, "invalid_count": 0, "warning_count": 0, "pricing_count": 0, "executable_opportunity_count": 0, "quoteable_opportunity_count": 0}
    expiry_at = datetime.combine(config.expiry_date, config.expiry_cutoff, TEHRAN)
    buy_fee, sell_fee = config.effective_option_fees()
    for index, snapshot in enumerate(snapshots):
        now = datetime.now(TEHRAN)
        books = {leg: states[leg][index] for leg in LEGS}
        hard_reasons: list[str] = []
        eligibility_reasons: list[str] = []
        warnings: list[str] = []
        for leg, book in books.items():
            if book is None:
                hard_reasons.append(f"missing_{leg}_book")
                continue
            hard_reasons.extend(book.validation_reasons(leg))
            if (snapshot - book.source_time).total_seconds() > config.max_quote_age_seconds:
                eligibility_reasons.append(f"stale_{leg}_book")
        source_times = [book.source_time for book in books.values() if book is not None]
        skew = int((max(source_times) - min(source_times)).total_seconds()) if len(source_times) == 4 else None
        if skew is not None and skew > config.max_cross_leg_skew_seconds:
            eligibility_reasons.append("cross_leg_quote_skew")
        ttm = max(0.0, (expiry_at - snapshot).total_seconds() / (365.25 * 86400))
        if ttm <= 0:
            hard_reasons.append("option_expired")
        benchmark, benchmark_source, curve, curve_reasons, curve_warnings = _benchmark(curves, snapshot, ttm, config)
        hard_reasons.extend(curve_reasons); warnings.extend(curve_warnings)
        reasons = hard_reasons + eligibility_reasons
        curve_time = datetime.combine(config.trade_date, time_from_hhmmss(int(curve[0])), TEHRAN) if curve else None
        row: dict[str, Any] = {
            "run_id": run_id, "trade_date": config.trade_date, "snapshot_time": snapshot,
            "underlying_instrument_code": config.underlying_instrument_code, "expiry_date": config.expiry_date,
            "lower_strike": config.lower_strike, "upper_strike": config.upper_strike,
            "box_width": config.upper_strike - config.lower_strike, "target_boxes": config.target_box_count,
            "multiplier": multiplier, "tick_size": tick_size, "cross_leg_skew_seconds": skew,
            "ttm_years": ttm, "benchmark_rate": benchmark, "benchmark_source": benchmark_source,
            "curve_time": curve_time,
            "curve_age_seconds": max(0, int((snapshot - curve_time).total_seconds())) if curve_time else None,
            "curve_beta0": curve[1] if curve else None, "curve_beta1": curve[2] if curve else None,
            "curve_beta2": curve[3] if curve else None, "curve_lambda": curve[4] if curve else None,
            "curve_rmse": curve[5] if curve else None, "curve_n_bonds": curve[6] if curve else None,
            "curve_converged": int(bool(curve[7])) if curve else None,
            "quality_status": "invalid" if reasons else "warning" if warnings else "valid",
            "quality_reasons": reasons, "warnings": warnings,
            "calculation_version": BOX_CALCULATION_VERSION, "calculated_at": now,
        }
        for leg, code in leg_codes.items():
            row.update(_book_fields(leg, code, books[leg], snapshot))
        snapshot_rows.append(row)
        counts["snapshot_count"] += 1
        if reasons:
            counts["invalid_count"] += 1
        else:
            counts["valid_count"] += 1
            if warnings:
                counts["warning_count"] += 1
        if not hard_reasons:
            priced = price_box(
                books=books, lower_strike=config.lower_strike, upper_strike=config.upper_strike,
                target_boxes=config.target_box_count, multiplier=multiplier, ttm_years=ttm,
                benchmark_rate=float(benchmark), minimum_ytm_spread_bps=config.minimum_ytm_spread_bps,
                buy_fee=buy_fee, sell_fee=sell_fee,
                settlement_cost_per_contract=config.settlement_cost_per_contract,
                tick_size=tick_size, calculated_at=now,
            )
            for pricing in priced:
                pricing.update(run_id=run_id, trade_date=config.trade_date, snapshot_time=snapshot)
                if eligibility_reasons:
                    pricing["opportunity"] = 0
                    pricing["classification"] = "ineligible_market_data"
                    pricing["quality_reasons"] = list(eligibility_reasons)
                for name in ("entry_debit", "entry_credit"):
                    per_share = pricing[f"{name}_per_share"]
                    pricing[f"{name}_per_contract"] = per_share * multiplier if per_share is not None else None
                    pricing[f"total_{name}"] = per_share * multiplier * config.target_box_count if per_share is not None else None
                pricing["opening_fee_per_contract"] = pricing["opening_fee_per_share"] * multiplier
                pricing["settlement_cost_per_contract"] = config.settlement_cost_per_contract
                pricing["terminal_cashflow_per_contract"] = pricing["terminal_cashflow_per_share"] * multiplier
                pricing["total_terminal_cashflow"] = pricing["terminal_cashflow_per_contract"] * config.target_box_count
                pricing_rows.append(pricing)
                if pricing["classification"] == "executable_opportunity":
                    counts["executable_opportunity_count"] += 1
                elif pricing["classification"] == "quoteable_opportunity":
                    counts["quoteable_opportunity_count"] += 1
            counts["pricing_count"] += len(priced)
        progress.advance(output_count=len(priced) if not hard_reasons else 0, warning_count=1 if warnings else 0)
    insert_snapshots(snapshot_rows, client)
    insert_pricings(pricing_rows, client)
    update_run(
        run_id, status="completed", result=counts, progress_current=len(snapshots),
        output_count=counts["pricing_count"], warning_count=counts["warning_count"], error="",
    )
    return counts


def fail_run(run_id: str, error: str) -> None:
    fail_operation_run(run_id, error)
