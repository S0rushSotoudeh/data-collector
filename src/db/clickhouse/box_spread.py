from __future__ import annotations

from datetime import date
from typing import Any

from clickhouse_connect.driver import Client

from src.db.clickhouse import _ensure_client, get_async_client


SNAPSHOTS_TABLE = "box_spread_snapshots"
PRICINGS_TABLE = "box_spread_pricings"

_LEG_FIELDS = (
    "instrument_code", "source_time", "age_seconds", "best_bid", "best_ask",
    "bid_total_volume", "ask_total_volume", "bid_order_count", "ask_order_count",
)
SNAPSHOT_COLUMNS = [
    "run_id", "trade_date", "snapshot_time", "underlying_instrument_code", "expiry_date",
    "lower_strike", "upper_strike", "box_width", "target_boxes", "multiplier", "tick_size",
    *[f"{leg}_{field}" for leg in ("c1", "c2", "p1", "p2") for field in _LEG_FIELDS],
    "cross_leg_skew_seconds", "ttm_years", "benchmark_rate", "benchmark_source",
    "curve_time", "curve_age_seconds", "curve_beta0", "curve_beta1", "curve_beta2",
    "curve_lambda", "curve_rmse", "curve_n_bonds", "curve_converged",
    "quality_status", "quality_reasons", "warnings", "calculation_version", "calculated_at",
]
PRICING_COLUMNS = [
    "run_id", "trade_date", "snapshot_time", "direction", "execution_mode", "maker_leg",
    "maker_side", "target_boxes", "capacity_boxes", "feasible", "signed_entry_cost_per_share",
    "entry_debit_per_share", "entry_credit_per_share", "entry_debit_per_contract",
    "entry_credit_per_contract", "total_entry_debit", "total_entry_credit",
    "opening_fee_per_share", "opening_fee_per_contract", "settlement_cost_per_contract",
    "terminal_cashflow_per_share", "terminal_cashflow_per_contract", "total_terminal_cashflow",
    "implied_rate", "benchmark_rate", "benchmark_spread_bps", "threshold_bps", "opportunity",
    "review_anomaly", "classification", "current_maker_price", "queue_ahead_volume",
    "hedge_signed_cost_per_share", "target_signed_cost_per_share", "safe_maker_boundary",
    "suggested_maker_price", "headroom", "quality_reasons", "calculation_version", "calculated_at",
]


def insert_snapshots(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if rows:
        c = _ensure_client(client)
        c.insert(SNAPSHOTS_TABLE, [tuple(row.get(name) for name in SNAPSHOT_COLUMNS) for row in rows], column_names=SNAPSHOT_COLUMNS)


def insert_pricings(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if rows:
        c = _ensure_client(client)
        c.insert(PRICINGS_TABLE, [tuple(row.get(name) for name in PRICING_COLUMNS) for row in rows], column_names=PRICING_COLUMNS)


def _dict_rows(result) -> list[dict[str, Any]]:
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def _where(
    *, run_id: str | None = None, trade_date: date | None = None,
    underlying_instrument_code: str | None = None, direction: str | None = None,
    execution_mode: str | None = None, classification: str | None = None,
    quality_status: str | None = None, opportunity: int | None = None,
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    fields = (
        ("run_id", "rid", "UUID", run_id), ("trade_date", "day", "Date", trade_date),
        ("underlying_instrument_code", "underlying", "String", underlying_instrument_code),
        ("direction", "direction", "String", direction),
        ("execution_mode", "mode", "String", execution_mode),
        ("classification", "classification", "String", classification),
        ("quality_status", "quality", "String", quality_status),
        ("opportunity", "opportunity", "UInt8", opportunity),
    )
    for column, key, kind, value in fields:
        if value is not None:
            clauses.append(f"{column} = {{{key}:{kind}}}")
            params[key] = value
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


async def get_snapshots(run_id: str, limit: int = 50000) -> list[dict[str, Any]]:
    client = await get_async_client()
    result = await client.query(
        f"SELECT * FROM `{SNAPSHOTS_TABLE}` WHERE run_id = {{rid:UUID}} ORDER BY snapshot_time LIMIT {{lim:UInt32}}",
        parameters={"rid": run_id, "lim": limit},
    )
    return _dict_rows(result)


async def get_pricings(run_id: str, limit: int = 50000) -> list[dict[str, Any]]:
    client = await get_async_client()
    result = await client.query(
        f"SELECT * FROM `{PRICINGS_TABLE}` WHERE run_id = {{rid:UUID}} "
        "ORDER BY snapshot_time, direction, execution_mode, maker_leg LIMIT {lim:UInt32}",
        parameters={"rid": run_id, "lim": limit},
    )
    return _dict_rows(result)


async def count_snapshots(**filters: Any) -> int:
    client = await get_async_client()
    where, params = _where(**filters)
    result = await client.query(f"SELECT count() FROM `{SNAPSHOTS_TABLE}` {where}", parameters=params)
    return int(result.result_rows[0][0]) if result.result_rows else 0


async def get_snapshots_paginated(offset: int = 0, limit: int = 100, **filters: Any) -> list[dict[str, Any]]:
    client = await get_async_client()
    where, params = _where(**filters)
    params.update(lim=limit, off=offset)
    result = await client.query(
        f"SELECT * FROM `{SNAPSHOTS_TABLE}` {where} ORDER BY snapshot_time DESC "
        "LIMIT {lim:UInt32} OFFSET {off:UInt32}", parameters=params,
    )
    return _dict_rows(result)


async def count_pricings(**filters: Any) -> int:
    client = await get_async_client()
    where, params = _where(**filters)
    result = await client.query(f"SELECT count() FROM `{PRICINGS_TABLE}` {where}", parameters=params)
    return int(result.result_rows[0][0]) if result.result_rows else 0


async def get_pricings_paginated(offset: int = 0, limit: int = 100, **filters: Any) -> list[dict[str, Any]]:
    client = await get_async_client()
    where, params = _where(**filters)
    params.update(lim=limit, off=offset)
    result = await client.query(
        f"SELECT * FROM `{PRICINGS_TABLE}` {where} ORDER BY snapshot_time DESC, direction, execution_mode, maker_leg "
        "LIMIT {lim:UInt32} OFFSET {off:UInt32}", parameters=params,
    )
    return _dict_rows(result)
