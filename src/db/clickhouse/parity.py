from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from clickhouse_connect.driver import Client

from src.db.clickhouse import _ensure_client, get_async_client

RUNS_TABLE = "parity_analysis_runs"
SNAPSHOTS_TABLE = "parity_analysis_snapshots"

RUN_COLUMNS = [
    "run_id", "underlying_instrument_code", "call_instrument_code", "put_instrument_code", "strike", "expiry_date",
    "start_date", "end_date", "start_time", "end_time", "interval_seconds",
    "max_quote_age_seconds", "expiry_cutoff", "margin_value", "margin_unit",
    "margin_per_share", "minimum_ytm_spread_bps", "funding_source",
    "manual_borrowing_rate", "borrowing_spread", "stock_fee_category",
    "option_fee_category", "stock_buy_fee", "stock_sell_fee", "call_buy_fee",
    "call_sell_fee", "put_buy_fee", "put_sell_fee", "multiplier", "tick_size",
    "calculation_version", "config_json", "status", "snapshot_count", "valid_count",
    "warning_count", "invalid_count", "opportunity_count", "error", "created_at", "updated_at",
]

SNAPSHOT_COLUMNS = [
    "run_id", "trade_date", "snapshot_time", "underlying_instrument_code",
    "call_instrument_code", "put_instrument_code", "strike", "expiry_at", "ttm_years",
    "multiplier", "tick_size", "required_margin", "stock_bid", "stock_ask",
    "stock_bid_volume", "stock_ask_volume", "stock_source_time", "stock_age_seconds",
    "call_bid", "call_ask", "call_bid_volume", "call_ask_volume", "call_source_time",
    "call_age_seconds", "put_bid", "put_ask", "put_bid_volume", "put_ask_volume",
    "put_source_time", "put_age_seconds", "borrowing_source", "borrowing_rate",
    "borrowing_curve_time", "borrowing_curve_age_seconds", "borrowing_beta0", "borrowing_beta1",
    "borrowing_beta2", "borrowing_lambda", "borrowing_converged", "borrowing_n_bonds", "borrowing_rmse",
    "stock_buy_fee", "stock_sell_fee", "call_buy_fee", "call_sell_fee", "put_buy_fee", "put_sell_fee",
    "pv_borrowing", "target_ytm", "target_capital_per_share",
    "target_package_count", "cross_leg_skew_seconds",
    "stock_bid_depth_volume", "stock_ask_depth_volume", "call_bid_depth_volume", "call_ask_depth_volume", "put_bid_depth_volume", "put_ask_depth_volume",
    "direct_take_capital_per_share", "direct_take_capital_per_contract", "direct_take_total_capital", "direct_take_opening_fee",
    "direct_take_expiry_profit_per_share", "direct_take_expiry_profit_per_contract", "direct_take_total_expiry_profit",
    "direct_take_holding_return", "direct_take_ytm", "direct_take_ytm_spread_bps", "direct_take_capacity", "direct_take_opportunity",
    *[f"{strategy}_{field}" for strategy in ("make_call_ask", "make_put_bid", "make_underlying_bid") for field in (
        "maker_price", "gross_edge", "opening_fee", "estimated_closing_fee", "net_edge", "surplus_edge",
        "gross_edge_per_contract", "net_edge_per_contract", "surplus_edge_per_contract", "total_value",
        "profitable_boundary", "suggested_maker_price", "headroom")],
    *[f"{strategy}_{field}" for strategy in ("make_call_ask", "make_put_bid", "make_underlying_bid") for field in (
        "target_boundary", "capital_per_share", "capital_per_contract", "total_capital",
        "expiry_profit_per_share", "expiry_profit_per_contract", "total_expiry_profit",
        "holding_return", "ytm", "ytm_spread_bps")],
    *[f"{strategy}_{field}" for strategy in ("make_call_ask", "make_put_bid", "make_underlying_bid") for field in ("opportunity", "capacity", "limiting_legs")],
    *[f"{strategy}_{field}" for strategy in ("make_call_ask", "make_put_bid", "make_underlying_bid") for field in ("quoteable", "queue_ahead_volume")],
    "quality_status", "quality_reasons", "warnings", "calculated_at", "calculation_version",
]

RUNS_DDL = f"""
CREATE TABLE IF NOT EXISTS `{RUNS_TABLE}` (
 run_id UUID, underlying_instrument_code String, call_instrument_code String, put_instrument_code String,
 strike Float64, expiry_date Date,
 start_date Date, end_date Date, start_time String, end_time String, interval_seconds UInt16,
 max_quote_age_seconds UInt32, expiry_cutoff String, margin_value Float64, margin_unit LowCardinality(String),
 margin_per_share Float64, minimum_ytm_spread_bps Nullable(Float64), funding_source LowCardinality(String),
 manual_borrowing_rate Nullable(Float64), borrowing_spread Nullable(Float64),
 stock_fee_category LowCardinality(String), option_fee_category LowCardinality(String),
 stock_buy_fee Float64, stock_sell_fee Float64, call_buy_fee Float64, call_sell_fee Float64,
 put_buy_fee Float64, put_sell_fee Float64, multiplier UInt32, tick_size Nullable(Float64),
 calculation_version LowCardinality(String), config_json String, status LowCardinality(String),
 snapshot_count UInt64, valid_count UInt64, warning_count UInt64, invalid_count UInt64,
 opportunity_count UInt64, error String, created_at DateTime64(3), updated_at DateTime64(3)
) ENGINE = ReplacingMergeTree(updated_at) ORDER BY (run_id)
"""

_QUOTE_FIELDS = """
 stock_bid Nullable(Float64), stock_ask Nullable(Float64), stock_bid_volume Nullable(UInt64),
 stock_ask_volume Nullable(UInt64), stock_source_time Nullable(DateTime64(3, 'Asia/Tehran')),
 stock_age_seconds Nullable(UInt32), call_bid Nullable(Float64), call_ask Nullable(Float64),
 call_bid_volume Nullable(UInt64), call_ask_volume Nullable(UInt64),
 call_source_time Nullable(DateTime64(3, 'Asia/Tehran')), call_age_seconds Nullable(UInt32),
 put_bid Nullable(Float64), put_ask Nullable(Float64), put_bid_volume Nullable(UInt64),
 put_ask_volume Nullable(UInt64), put_source_time Nullable(DateTime64(3, 'Asia/Tehran')),
 put_age_seconds Nullable(UInt32)
"""

_STRATEGIES = ("make_call_ask", "make_put_bid", "make_underlying_bid")
_STRATEGY_FLOATS = ("maker_price", "gross_edge", "opening_fee", "estimated_closing_fee", "net_edge", "surplus_edge", "gross_edge_per_contract", "net_edge_per_contract", "surplus_edge_per_contract", "total_value", "profitable_boundary", "suggested_maker_price", "headroom")
_V3_STRATEGY_FLOATS = (
    "target_boundary", "capital_per_share", "capital_per_contract", "total_capital",
    "expiry_profit_per_share", "expiry_profit_per_contract", "total_expiry_profit",
    "holding_return", "ytm", "ytm_spread_bps",
)

SNAPSHOTS_DDL = f"""
CREATE TABLE IF NOT EXISTS `{SNAPSHOTS_TABLE}` (
 run_id UUID, trade_date Date, snapshot_time DateTime64(3, 'Asia/Tehran'),
 underlying_instrument_code String, call_instrument_code String, put_instrument_code String,
 strike Float64, expiry_at DateTime64(3, 'Asia/Tehran'), ttm_years Float64,
 multiplier UInt32, tick_size Nullable(Float64), required_margin Float64,
 {_QUOTE_FIELDS}, borrowing_source LowCardinality(String), borrowing_rate Nullable(Float64),
 borrowing_curve_time Nullable(DateTime64(3, 'Asia/Tehran')),
 borrowing_curve_age_seconds Nullable(Float64), borrowing_beta0 Nullable(Float64), borrowing_beta1 Nullable(Float64), borrowing_beta2 Nullable(Float64), borrowing_lambda Nullable(Float64),
 borrowing_converged Nullable(UInt8), borrowing_n_bonds Nullable(UInt16), borrowing_rmse Nullable(Float64),
 stock_buy_fee Float64, stock_sell_fee Float64, call_buy_fee Float64, call_sell_fee Float64,
 put_buy_fee Float64, put_sell_fee Float64,
 pv_borrowing Nullable(Float64), target_ytm Nullable(Float64), target_capital_per_share Nullable(Float64),
 target_package_count UInt64 DEFAULT 1, cross_leg_skew_seconds Nullable(UInt32),
 stock_bid_depth_volume UInt64 DEFAULT 0, stock_ask_depth_volume UInt64 DEFAULT 0,
 call_bid_depth_volume UInt64 DEFAULT 0, call_ask_depth_volume UInt64 DEFAULT 0,
 put_bid_depth_volume UInt64 DEFAULT 0, put_ask_depth_volume UInt64 DEFAULT 0,
 direct_take_capital_per_share Nullable(Float64), direct_take_capital_per_contract Nullable(Float64), direct_take_total_capital Nullable(Float64), direct_take_opening_fee Nullable(Float64),
 direct_take_expiry_profit_per_share Nullable(Float64), direct_take_expiry_profit_per_contract Nullable(Float64), direct_take_total_expiry_profit Nullable(Float64),
 direct_take_holding_return Nullable(Float64), direct_take_ytm Nullable(Float64), direct_take_ytm_spread_bps Nullable(Float64), direct_take_capacity UInt64 DEFAULT 0, direct_take_opportunity UInt8 DEFAULT 0,
 {', '.join(f'{s}_{f} Nullable(Float64)' for s in _STRATEGIES for f in _STRATEGY_FLOATS)},
 {', '.join(f'{s}_{f} Nullable(Float64)' for s in _STRATEGIES for f in _V3_STRATEGY_FLOATS)},
 {', '.join(f'{s}_opportunity Nullable(UInt8), {s}_capacity Nullable(UInt64), {s}_limiting_legs Array(LowCardinality(String))' for s in _STRATEGIES)},
 {', '.join(f'{s}_quoteable UInt8 DEFAULT 0, {s}_queue_ahead_volume UInt64 DEFAULT 0' for s in _STRATEGIES)},
 quality_status LowCardinality(String), quality_reasons Array(String), warnings Array(String),
 calculated_at DateTime64(3), calculation_version LowCardinality(String)
) ENGINE = MergeTree PARTITION BY toYYYYMM(trade_date)
ORDER BY (run_id, trade_date, snapshot_time)
"""


def insert_run(row: dict[str, Any], client: Client | None = None) -> None:
    c = _ensure_client(client)
    c.insert(RUNS_TABLE, [tuple(row.get(k) for k in RUN_COLUMNS)], column_names=RUN_COLUMNS)


def insert_snapshots(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    c.insert(SNAPSHOTS_TABLE, [tuple(row.get(k) for k in SNAPSHOT_COLUMNS) for row in rows], column_names=SNAPSHOT_COLUMNS)


def _dict_rows(result) -> list[dict[str, Any]]:
    names = result.column_names
    return [dict(zip(names, row)) for row in result.result_rows]


async def list_runs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    c = await get_async_client()
    result = await c.query(
        f"SELECT * FROM `{RUNS_TABLE}` FINAL ORDER BY created_at DESC LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}",
        parameters={"lim": limit, "off": offset},
    )
    return _dict_rows(result)


def _admin_filters(
    *,
    run_id: str | None = None,
    underlying_instrument_code: str | None = None,
    status: str | None = None,
    trade_date: date | None = None,
    quality_status: str | None = None,
    opportunity: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if run_id:
        clauses.append("toString(run_id) = {run_id:String}")
        params["run_id"] = run_id
    if underlying_instrument_code:
        clauses.append("underlying_instrument_code = {underlying:String}")
        params["underlying"] = underlying_instrument_code
    if status:
        clauses.append("status = {status:String}")
        params["status"] = status
    if trade_date:
        clauses.append("trade_date = {trade_date:Date}")
        params["trade_date"] = trade_date
    if quality_status:
        clauses.append("quality_status = {quality_status:String}")
        params["quality_status"] = quality_status
    if opportunity is not None:
        operator = "OR" if opportunity else "AND"
        clauses.append("(" + f" {operator} ".join(
            f"{strategy}_opportunity = {{opportunity:UInt8}}" for strategy in _STRATEGIES
        ) + ")")
        params["opportunity"] = opportunity
    return clauses, params


async def count_runs(
    run_id: str | None = None,
    underlying_instrument_code: str | None = None,
    status: str | None = None,
) -> int:
    client = await get_async_client()
    clauses, params = _admin_filters(
        run_id=run_id,
        underlying_instrument_code=underlying_instrument_code,
        status=status,
    )
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await client.query(
        f"SELECT count() FROM `{RUNS_TABLE}` FINAL{where}", parameters=params
    )
    return int(result.result_rows[0][0])


async def get_runs_paginated(
    run_id: str | None = None,
    underlying_instrument_code: str | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    clauses, params = _admin_filters(
        run_id=run_id,
        underlying_instrument_code=underlying_instrument_code,
        status=status,
    )
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.update({"limit": limit, "offset": offset})
    result = await client.query(
        f"SELECT * FROM `{RUNS_TABLE}` FINAL{where} "
        "ORDER BY created_at DESC LIMIT {limit:UInt32} OFFSET {offset:UInt32}",
        parameters=params,
    )
    return _dict_rows(result)


async def count_snapshots(
    run_id: str | None = None,
    trade_date: date | None = None,
    underlying_instrument_code: str | None = None,
    quality_status: str | None = None,
    opportunity: int | None = None,
) -> int:
    client = await get_async_client()
    clauses, params = _admin_filters(
        run_id=run_id,
        trade_date=trade_date,
        underlying_instrument_code=underlying_instrument_code,
        quality_status=quality_status,
        opportunity=opportunity,
    )
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await client.query(
        f"SELECT count() FROM `{SNAPSHOTS_TABLE}`{where}", parameters=params
    )
    return int(result.result_rows[0][0])


async def get_snapshots_paginated(
    run_id: str | None = None,
    trade_date: date | None = None,
    underlying_instrument_code: str | None = None,
    quality_status: str | None = None,
    opportunity: int | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    clauses, params = _admin_filters(
        run_id=run_id,
        trade_date=trade_date,
        underlying_instrument_code=underlying_instrument_code,
        quality_status=quality_status,
        opportunity=opportunity,
    )
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.update({"limit": limit, "offset": offset})
    result = await client.query(
        f"SELECT * FROM `{SNAPSHOTS_TABLE}`{where} "
        "ORDER BY trade_date DESC, snapshot_time DESC "
        "LIMIT {limit:UInt32} OFFSET {offset:UInt32}",
        parameters=params,
    )
    return _dict_rows(result)


async def get_run(run_id: str) -> dict[str, Any] | None:
    c = await get_async_client()
    result = await c.query(
        f"SELECT * FROM `{RUNS_TABLE}` FINAL WHERE run_id = {{rid:UUID}} LIMIT 1",
        parameters={"rid": run_id},
    )
    rows = _dict_rows(result)
    return rows[0] if rows else None


async def get_snapshots(
    run_id: str, trade_date: date | None = None, start_time: time | None = None,
    end_time: time | None = None, limit: int = 10000,
) -> list[dict[str, Any]]:
    c = await get_async_client()
    clauses = ["run_id = {rid:UUID}"]
    params: dict[str, Any] = {"rid": run_id, "lim": limit}
    if trade_date:
        clauses.append("trade_date = {dt:Date}"); params["dt"] = trade_date
    if start_time:
        clauses.append("formatDateTime(snapshot_time, '%H:%M:%S') >= {st:String}"); params["st"] = start_time.isoformat()
    if end_time:
        clauses.append("formatDateTime(snapshot_time, '%H:%M:%S') <= {et:String}"); params["et"] = end_time.isoformat()
    result = await c.query(
        f"SELECT * FROM `{SNAPSHOTS_TABLE}` WHERE {' AND '.join(clauses)} "
        "ORDER BY trade_date, snapshot_time LIMIT {lim:UInt32}", parameters=params,
    )
    return _dict_rows(result)
