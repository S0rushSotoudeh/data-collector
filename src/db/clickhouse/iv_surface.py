from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any

from clickhouse_connect.driver import Client

from src.db.clickhouse import _ensure_client, get_async_client

RUNS_TABLE = "iv_surface_runs"
POINTS_TABLE = "option_iv_points"
FITS_TABLE = "orc_wing_fits"
CONTRACT_DAILY_TABLE = "option_contract_daily"
PAIR_DAILY_TABLE = "option_pair_daily"

RUN_COLUMNS = [
    "run_id", "underlying_instrument_code", "start_date", "end_date", "session_start", "session_end",
    "interval_seconds", "max_quote_age_seconds", "forward_source", "rate_source",
    "pricing_convention_id", "pricing_convention_version", "model_version", "config_json", "status",
    "target_snapshot_count", "completed_snapshot_count", "point_count", "fit_count", "warning_count",
    "quality_summary", "error", "created_at", "updated_at",
]
POINT_COLUMNS = [
    "run_id", "snapshot_time", "trade_date", "underlying_instrument_code", "instrument_code",
    "option_type", "side", "strike", "expiry_date", "ttm_years", "forward_lower", "forward_upper",
    "forward", "rate", "rate_source", "price", "iv", "vega", "depth", "quote_time",
    "quote_age_seconds", "weight", "rejection_reason", "created_at",
]
FIT_COLUMNS = [
    "run_id", "snapshot_time", "trade_date", "underlying_instrument_code", "expiry_date", "side",
    "forward", "ttm_years", "vc", "sc", "pc", "cc", "dc", "uc", "dsm", "usm", "rmse",
    "point_count", "converged", "quality_flags", "created_at",
]


def insert_run(row: dict[str, Any], client: Client | None = None) -> None:
    c = _ensure_client(client)
    c.insert(RUNS_TABLE, [tuple(row.get(name) for name in RUN_COLUMNS)], column_names=RUN_COLUMNS)


def insert_points(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if rows:
        c = _ensure_client(client)
        c.insert(POINTS_TABLE, [tuple(row.get(name) for name in POINT_COLUMNS) for row in rows], column_names=POINT_COLUMNS)


def insert_fits(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if rows:
        c = _ensure_client(client)
        c.insert(FITS_TABLE, [tuple(row.get(name) for name in FIT_COLUMNS) for row in rows], column_names=FIT_COLUMNS)


def _dict_rows(result) -> list[dict[str, Any]]:
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


async def list_runs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    client = await get_async_client()
    result = await client.query(
        f"SELECT * FROM `{RUNS_TABLE}` FINAL ORDER BY created_at DESC LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}",
        parameters={"lim": limit, "off": offset},
    )
    return _dict_rows(result)


async def get_run(run_id: str) -> dict[str, Any] | None:
    client = await get_async_client()
    result = await client.query(
        f"SELECT * FROM `{RUNS_TABLE}` FINAL WHERE run_id = {{rid:UUID}} LIMIT 1", parameters={"rid": run_id}
    )
    rows = _dict_rows(result)
    return rows[0] if rows else None


async def get_points(run_id: str, limit: int = 50000) -> list[dict[str, Any]]:
    client = await get_async_client()
    result = await client.query(
        f"SELECT * FROM `{POINTS_TABLE}` WHERE run_id = {{rid:UUID}} "
        "ORDER BY snapshot_time, expiry_date, strike, side LIMIT {lim:UInt32}",
        parameters={"rid": run_id, "lim": limit},
    )
    return _dict_rows(result)


async def get_fits(run_id: str, limit: int = 50000) -> list[dict[str, Any]]:
    client = await get_async_client()
    result = await client.query(
        f"SELECT * FROM `{FITS_TABLE}` WHERE run_id = {{rid:UUID}} "
        "ORDER BY snapshot_time, expiry_date, side LIMIT {lim:UInt32}",
        parameters={"rid": run_id, "lim": limit},
    )
    return _dict_rows(result)


def _analytics_where(
    *,
    run_id: str | None = None,
    trade_date: date | None = None,
    underlying_instrument_code: str | None = None,
    instrument_code: str | None = None,
    option_type: str | None = None,
    side: str | None = None,
    expiry_date: date | None = None,
    rejection_reason: str | None = None,
    converged: int | None = None,
    quality_flag: str | None = None,
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    filters = (
        ("run_id", "rid", "UUID", run_id),
        ("trade_date", "day", "Date", trade_date),
        ("underlying_instrument_code", "underlying", "String", underlying_instrument_code),
        ("instrument_code", "instrument", "String", instrument_code),
        ("option_type", "option_type", "String", option_type),
        ("side", "side", "String", side),
        ("expiry_date", "expiry", "Date", expiry_date),
        ("rejection_reason", "rejection", "String", rejection_reason),
        ("converged", "converged", "UInt8", converged),
    )
    for column, parameter, ch_type, value in filters:
        if value is not None:
            clauses.append(f"{column} = {{{parameter}:{ch_type}}}")
            params[parameter] = value
    if quality_flag:
        clauses.append("has(quality_flags, {quality_flag:String})")
        params["quality_flag"] = quality_flag
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


async def get_iv_points_paginated(
    run_id: str | None = None,
    trade_date: date | None = None,
    underlying_instrument_code: str | None = None,
    instrument_code: str | None = None,
    option_type: str | None = None,
    side: str | None = None,
    expiry_date: date | None = None,
    rejection_reason: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where, params = _analytics_where(
        run_id=run_id,
        trade_date=trade_date,
        underlying_instrument_code=underlying_instrument_code,
        instrument_code=instrument_code,
        option_type=option_type,
        side=side,
        expiry_date=expiry_date,
        rejection_reason=rejection_reason,
    )
    params.update(lim=limit, off=offset)
    result = await client.query(
        f"SELECT * FROM `{POINTS_TABLE}` {where} "
        "ORDER BY snapshot_time DESC, expiry_date, side, strike, instrument_code "
        "LIMIT {lim:UInt32} OFFSET {off:UInt32}",
        parameters=params,
    )
    return _dict_rows(result)


async def count_iv_points(
    run_id: str | None = None,
    trade_date: date | None = None,
    underlying_instrument_code: str | None = None,
    instrument_code: str | None = None,
    option_type: str | None = None,
    side: str | None = None,
    expiry_date: date | None = None,
    rejection_reason: str | None = None,
) -> int:
    client = await get_async_client()
    where, params = _analytics_where(
        run_id=run_id,
        trade_date=trade_date,
        underlying_instrument_code=underlying_instrument_code,
        instrument_code=instrument_code,
        option_type=option_type,
        side=side,
        expiry_date=expiry_date,
        rejection_reason=rejection_reason,
    )
    result = await client.query(f"SELECT count() FROM `{POINTS_TABLE}` {where}", parameters=params)
    return int(result.result_rows[0][0]) if result.result_rows else 0


async def get_orc_wing_fits_paginated(
    run_id: str | None = None,
    trade_date: date | None = None,
    underlying_instrument_code: str | None = None,
    expiry_date: date | None = None,
    side: str | None = None,
    converged: int | None = None,
    quality_flag: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where, params = _analytics_where(
        run_id=run_id,
        trade_date=trade_date,
        underlying_instrument_code=underlying_instrument_code,
        expiry_date=expiry_date,
        side=side,
        converged=converged,
        quality_flag=quality_flag,
    )
    params.update(lim=limit, off=offset)
    result = await client.query(
        f"SELECT * FROM `{FITS_TABLE}` {where} "
        "ORDER BY snapshot_time DESC, expiry_date, side "
        "LIMIT {lim:UInt32} OFFSET {off:UInt32}",
        parameters=params,
    )
    return _dict_rows(result)


async def count_orc_wing_fits(
    run_id: str | None = None,
    trade_date: date | None = None,
    underlying_instrument_code: str | None = None,
    expiry_date: date | None = None,
    side: str | None = None,
    converged: int | None = None,
    quality_flag: str | None = None,
) -> int:
    client = await get_async_client()
    where, params = _analytics_where(
        run_id=run_id,
        trade_date=trade_date,
        underlying_instrument_code=underlying_instrument_code,
        expiry_date=expiry_date,
        side=side,
        converged=converged,
        quality_flag=quality_flag,
    )
    result = await client.query(f"SELECT count() FROM `{FITS_TABLE}` {where}", parameters=params)
    return int(result.result_rows[0][0]) if result.result_rows else 0


async def market_potential(section: str, start_date: date | None = None, end_date: date | None = None, limit: int = 1000) -> list[dict[str, Any]]:
    client = await get_async_client()
    clauses, params = [], {"lim": limit}
    if start_date:
        clauses.append("trade_date >= {start:Date}"); params["start"] = start_date
    if end_date:
        clauses.append("trade_date <= {end:Date}"); params["end"] = end_date
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    if section in {"contracts", "timeseries"}:
        order = "trade_date DESC, traded_value DESC" if section == "contracts" else "trade_date, instrument_code"
        result = await client.query(
            f"SELECT * FROM `{CONTRACT_DAILY_TABLE}`{where} ORDER BY {order} LIMIT {{lim:UInt32}}", parameters=params
        )
    elif section == "pairs":
        result = await client.query(
            f"SELECT * FROM `{PAIR_DAILY_TABLE}`{where} ORDER BY trade_date DESC, activity_score DESC LIMIT {{lim:UInt32}}", parameters=params
        )
    else:
        raise ValueError("unsupported market-potential section")
    return _dict_rows(result)


async def market_potential_summary(start_date: date | None = None, end_date: date | None = None) -> dict[str, Any]:
    client = await get_async_client()
    clauses, params = [], {}
    if start_date:
        clauses.append("trade_date >= {start:Date}"); params["start"] = start_date
    if end_date:
        clauses.append("trade_date <= {end:Date}"); params["end"] = end_date
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    result = await client.query(
        f"SELECT countDistinct(instrument_code) contracts, countDistinct(underlying_instrument_code) underlyings, "
        f"sum(trade_count) trades, sum(traded_value) traded_value, avg(two_sided_ratio) two_sided_ratio "
        f"FROM `{CONTRACT_DAILY_TABLE}`{where}", parameters=params,
    )
    names = result.column_names
    if not result.result_rows:
        return {}
    return {
        name: (None if isinstance(value, float) and not math.isfinite(value) else value)
        for name, value in zip(names, result.result_rows[0])
    }


async def coverage() -> dict[str, Any]:
    client = await get_async_client()
    tables = ("option_order_book", "option_trades", "stock_order_book", "stock_trades")
    output: dict[str, Any] = {}
    for table in tables:
        result = await client.query(f"SELECT min(trade_date), max(trade_date), count() FROM `{table}`")
        output[table] = dict(zip(("start_date", "end_date", "row_count"), result.result_rows[0]))
    return output
