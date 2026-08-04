from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.analytics.parity import (
    CALCULATION_VERSION, Book, calculate, validate_book,
)
from src.analytics.parity_config import ParityRunConfig
from src.analytics.yield_curve import ns_yield
from src.db.clickhouse import get_client
from src.db.clickhouse.parity import (
    SNAPSHOT_COLUMNS,
    insert_snapshots,
)
from src.services.operation_runs import fail_run as fail_operation_run
from src.services.operation_runs import get_run, run_to_dict, update_progress, update_run

TEHRAN = ZoneInfo("Asia/Tehran")


def hhmmss(value: time) -> int:
    return value.hour * 10000 + value.minute * 100 + value.second


def time_from_hhmmss(value: int) -> time:
    return time(value // 10000, (value // 100) % 100, value % 100)


def aligned_snapshots(day: date, start: time, end: time, interval: int) -> list[datetime]:
    start_seconds = start.hour * 3600 + start.minute * 60 + start.second
    end_seconds = end.hour * 3600 + end.minute * 60 + end.second
    first = ((start_seconds + interval - 1) // interval) * interval
    base = datetime.combine(day, time(), TEHRAN)
    return [base + timedelta(seconds=s) for s in range(first, end_seconds + 1, interval)]


def latest_state_rows(rows: list[tuple], snapshots: list[datetime]) -> list[tuple | None]:
    """Latest-at-or-before state, with same-day seeding and no daily carry."""
    result: list[tuple | None] = []
    index = 0
    state = None
    for snapshot in snapshots:
        cutoff = hhmmss(snapshot.timetz().replace(tzinfo=None))
        while index < len(rows) and int(rows[index][0]) <= cutoff:
            state = rows[index]
            index += 1
        result.append(state)
    return result


def _run_row(client, run_id: str) -> dict[str, Any]:
    operation = get_run(run_id)
    if operation is None or operation.family != "parity":
        raise ValueError("unknown parity run")
    return run_to_dict(operation)


def _update_run(client, row: dict[str, Any], status: str, **counts: Any) -> None:
    row.update(counts, status=status, updated_at=datetime.now(TEHRAN))
    if status == "running":
        update_progress(
            row["run_id"],
            current=int(counts.get("snapshot_count", row.get("snapshot_count", 0)) or 0),
            output_count=int(counts.get("snapshot_count", row.get("snapshot_count", 0)) or 0),
            warning_count=int(counts.get("warning_count", row.get("warning_count", 0)) or 0),
            result={key: row.get(key, 0) for key in ("snapshot_count", "valid_count", "warning_count", "invalid_count", "opportunity_count")},
        )
    else:
        update_run(
            row["run_id"], status=status,
            result={key: row.get(key, 0) for key in ("snapshot_count", "valid_count", "warning_count", "invalid_count", "opportunity_count")},
            progress_current=int(row.get("snapshot_count", 0) or 0),
            output_count=int(row.get("snapshot_count", 0) or 0),
            warning_count=int(row.get("warning_count", 0) or 0),
            error=str(row.get("error") or ""),
        )


def _quotes(client, table: str, code: str, day: date, end: time) -> list[tuple]:
    return client.query(
        f"SELECT trade_time, bid_price, ask_price, bid_volume, ask_volume "
        f"FROM `{table}` FINAL WHERE instrument_code = {{code:String}} AND trade_date = {{day:Date}} "
        "AND depth_level = 1 AND trade_time <= {end:UInt32} ORDER BY trade_time, ingested_at",
        parameters={"code": code, "day": day, "end": hhmmss(end)},
    ).result_rows


def _curves(client, day: date, end: time) -> dict[str, list[tuple]]:
    rows = client.query(
        "SELECT trade_time, curve_side, beta0, beta1, beta2, lambda, rmse, n_bonds, converged "
        "FROM yield_curve_fits FINAL WHERE trade_date = {day:Date} AND trade_time <= {end:UInt32} "
        "ORDER BY trade_time",
        parameters={"day": day, "end": hhmmss(end)},
    ).result_rows
    return {side: [r for r in rows if r[1] == side] for side in ("bid", "ask")}


def _latest_curve(rows: list[tuple], snapshot: datetime) -> tuple | None:
    cutoff = hhmmss(snapshot.timetz().replace(tzinfo=None))
    current = None
    for row in rows:
        if row[0] > cutoff:
            break
        current = row
    return current


def _quote_fields(prefix: str, row: tuple | None, snapshot: datetime) -> tuple[dict[str, Any], Book | None]:
    if row is None:
        return {f"{prefix}_{key}": None for key in (
            "bid", "ask", "bid_volume", "ask_volume", "source_time", "age_seconds"
        )}, None
    source = datetime.combine(snapshot.date(), time_from_hhmmss(int(row[0])), TEHRAN)
    fields = {
        f"{prefix}_bid": float(row[1]), f"{prefix}_ask": float(row[2]),
        f"{prefix}_bid_volume": int(row[3]), f"{prefix}_ask_volume": int(row[4]),
        f"{prefix}_source_time": source,
        f"{prefix}_age_seconds": max(0, int((snapshot - source).total_seconds())),
    }
    return fields, Book(float(row[1]), float(row[2]), int(row[3]), int(row[4]))


def _curve_fields(prefix: str, curve: tuple | None, snapshot: datetime) -> dict[str, Any]:
    empty = {
        f"{prefix}_curve_time": None, f"{prefix}_curve_age_seconds": None,
        f"{prefix}_beta0": None, f"{prefix}_beta1": None, f"{prefix}_beta2": None,
        f"{prefix}_lambda": None, f"{prefix}_rmse": None, f"{prefix}_n_bonds": None,
        f"{prefix}_converged": None,
    }
    if curve is None:
        return empty
    curve_time = datetime.combine(snapshot.date(), time_from_hhmmss(int(curve[0])), TEHRAN)
    return {
        f"{prefix}_curve_time": curve_time,
        f"{prefix}_curve_age_seconds": max(0, (snapshot - curve_time).total_seconds()),
        f"{prefix}_beta0": curve[2], f"{prefix}_beta1": curve[3], f"{prefix}_beta2": curve[4],
        f"{prefix}_lambda": curve[5], f"{prefix}_rmse": curve[6],
        f"{prefix}_n_bonds": curve[7], f"{prefix}_converged": curve[8],
    }


def _effective_rate(
    manual: float | None, curve: tuple | None, ttm: float, label: str,
    reasons: list[str], warnings: list[str], snapshot: datetime,
) -> tuple[float | None, str]:
    if manual is not None:
        return manual, "manual"
    if curve is None:
        reasons.append(f"missing_{label}_curve")
        return None, "curve"
    if not curve[8] or any(v is None for v in curve[2:6]):
        reasons.append(f"non_converged_{label}_curve")
        return None, "curve"
    curve_time = datetime.combine(snapshot.date(), time_from_hhmmss(int(curve[0])), TEHRAN)
    if (snapshot - curve_time).total_seconds() > 60:
        warnings.append(f"{label}_curve_older_than_60_seconds")
    if int(curve[7]) < 4:
        warnings.append(f"{label}_curve_fewer_than_four_bonds")
    if curve[6] is not None and float(curve[6]) * 10_000 > 200:
        warnings.append(f"{label}_curve_rmse_over_200_bps")
    return ns_yield(ttm, float(curve[2]), float(curve[3]), float(curve[4]), float(curve[5])), "curve"


def process_run(run_id: str) -> dict[str, int]:
    client = get_client()
    stored = _run_row(client, run_id)
    if stored.get("calculation_version") != CALCULATION_VERSION:
        raise RuntimeError(
            f"Only {CALCULATION_VERSION} runs can be processed; finish or cancel queued older runs before deployment"
        )
    config = ParityRunConfig.model_validate_json(stored["config_json"])
    _update_run(client, stored, "running", error="")
    persisted_config = json.loads(stored["config_json"])
    strike = float(persisted_config["strike"])
    expiry_date = date.fromisoformat(persisted_config["expiry_date"])
    fees = config.effective_fees()
    counts = {"snapshot_count": 0, "valid_count": 0, "warning_count": 0, "invalid_count": 0, "opportunity_count": 0}
    batch: list[dict[str, Any]] = []
    day = config.start_date
    while day <= config.end_date:
        day_start = config.start_time
        day_end = config.end_time
        snapshots = aligned_snapshots(day, day_start, day_end, config.interval_seconds)
        stocks = latest_state_rows(_quotes(client, "stock_order_book", config.underlying_instrument_code, day, day_end), snapshots)
        calls = latest_state_rows(_quotes(client, "option_order_book", config.call_instrument_code, day, day_end), snapshots)
        puts = latest_state_rows(_quotes(client, "option_order_book", config.put_instrument_code, day, day_end), snapshots)
        curves = _curves(client, day, day_end)
        expiry_at = datetime.combine(expiry_date, config.expiry_cutoff, TEHRAN)
        for snapshot, stock_row, call_row, put_row in zip(snapshots, stocks, calls, puts):
            reasons: list[str] = []
            warnings: list[str] = []
            ttm = max(0.0, (expiry_at - snapshot).total_seconds() / (365.25 * 86400))
            row: dict[str, Any] = {
                "run_id": run_id, "trade_date": day, "snapshot_time": snapshot,
                "underlying_instrument_code": config.underlying_instrument_code,
                "call_instrument_code": config.call_instrument_code, "put_instrument_code": config.put_instrument_code,
                "strike": strike, "expiry_at": expiry_at, "ttm_years": ttm,
                "multiplier": config.multiplier, "tick_size": config.tick_size,
                "required_margin": 0.0, "calculated_at": datetime.now(TEHRAN),
                "calculation_version": CALCULATION_VERSION,
                **{f"{name}_fee": value for name, value in fees.__dict__.items()},
            }
            books = {}
            for name, raw in (("stock", stock_row), ("call", call_row), ("put", put_row)):
                fields, book = _quote_fields(name, raw, snapshot); row.update(fields); books[name] = book
                if book is None:
                    reasons.append(f"missing_{name}_quote")
                else:
                    reasons.extend(validate_book(book, name))
                    if fields[f"{name}_age_seconds"] > config.max_quote_age_seconds:
                        reasons.append(f"stale_{name}_quote")
            if snapshot >= expiry_at:
                reasons.append("option_expired")
            elif (expiry_at - snapshot).total_seconds() < 86400:
                warnings.append("less_than_one_day_to_expiry")

            ask_curve = _latest_curve(curves["ask"], snapshot)
            row.update(_curve_fields("borrowing", ask_curve, snapshot))
            borrowing, borrowing_source = _effective_rate(config.manual_borrowing_rate, ask_curve, ttm, "borrowing", reasons, warnings, snapshot)
            if borrowing is not None and config.manual_borrowing_rate is None and config.borrowing_spread is not None:
                borrowing += config.borrowing_spread; borrowing_source = "curve+spread"
            row.update(borrowing_rate=borrowing, borrowing_source=borrowing_source)
            if reasons:
                for key in SNAPSHOT_COLUMNS:
                    if key.startswith(("make_call_ask_", "make_put_bid_", "make_underlying_bid_")) or key == "pv_borrowing":
                        row.setdefault(key, [] if key.endswith("limiting_legs") else None)
                row["quality_status"] = "invalid"; counts["invalid_count"] += 1
            else:
                values = calculate(
                    call=books["call"], put=books["put"], stock=books["stock"], strike=strike,
                    ttm_years=ttm, borrowing_rate=borrowing, fees=fees,
                    minimum_ytm_spread_bps=config.minimum_ytm_spread_bps,
                    multiplier=config.multiplier, tick_size=config.tick_size,
                )
                row.update(values)
                row["quality_status"] = "warning" if warnings else "valid"
                counts["valid_count"] += 1
                if warnings: counts["warning_count"] += 1
                if any(values[f"{strategy}_opportunity"] for strategy in ("make_call_ask", "make_put_bid", "make_underlying_bid")):
                    counts["opportunity_count"] += 1
            row["quality_reasons"] = reasons; row["warnings"] = warnings
            for key in SNAPSHOT_COLUMNS:
                row.setdefault(key, [] if key.endswith("limiting_legs") else None)
            batch.append(row); counts["snapshot_count"] += 1
            if len(batch) >= 1000:
                insert_snapshots(batch, client); batch.clear()
        day += timedelta(days=1)
        _update_run(client, stored, "running", **counts, error="")
    insert_snapshots(batch, client)
    _update_run(client, stored, "completed", **counts, error="")
    return counts


def fail_run(run_id: str, error: str) -> None:
    fail_operation_run(run_id, error)
