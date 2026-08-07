from __future__ import annotations

from datetime import date, datetime
from typing import Any

from clickhouse_connect.driver import Client

from src.db.clickhouse import _ensure_client, get_async_client

UNIVERSE_TABLE = "option_mispricing_universe"
FITS_TABLE = "option_mispricing_fits"
OBSERVATIONS_TABLE = "option_mispricing_observations"
RANKINGS_TABLE = "option_mispricing_rankings"

UNIVERSE_COLUMNS = [
    "run_id", "trade_date", "instrument_code", "underlying_instrument_code", "option_type",
    "strike", "expiry_date", "listing_date", "quote_count", "two_sided_quote_count",
    "first_quote_time", "last_quote_time", "group_strike_count", "group_call_count", "group_put_count",
    "eligible", "eligibility_reasons", "model_version", "configuration_version",
    "pricing_convention_id", "pricing_convention_version", "frozen_at",
]
FIT_COLUMNS = [
    "run_id", "trade_date", "snapshot_time", "underlying_instrument_code", "expiry_date",
    "forward_lower", "forward_upper", "forward", "rate", "rate_source", "ttm_years",
    "vc", "sc", "pc", "cc", "dc", "uc", "dsm", "usm", "rmse", "point_count",
    "used_point_count", "excluded_point_count", "fit_passes", "converged",
    "excluded_instrument_codes", "excluded_reasons", "quality_status", "quality_flags", "created_at",
]
OBSERVATION_COLUMNS = [
    "run_id", "trade_date", "snapshot_time", "underlying_instrument_code", "instrument_code",
    "option_type", "strike", "expiry_date", "bid_price", "midpoint_price", "fair_price", "ask_price",
    "fair_iv", "bid_distance", "ask_distance", "midpoint_distance", "bid_distance_bps",
    "ask_distance_bps", "midpoint_distance_bps", "forward", "rate", "rate_source", "depth",
    "bid_depth", "ask_depth", "quote_time", "quote_age_seconds", "fit_rmse", "quality_status",
    "rejection_reason", "created_at",
]
RANKING_COLUMNS = [
    "run_id", "trade_date", "underlying_instrument_code", "valid_contract_count", "valid_expiry_count",
    "valid_snapshot_count", "total_snapshot_count", "snapshot_coverage", "median_abs_midpoint_bps",
    "p90_abs_midpoint_bps", "largest_bid_deviation_bps", "largest_ask_deviation_bps",
    "outside_25_count", "outside_25_share", "outside_50_count", "outside_50_share",
    "outside_100_count", "outside_100_share", "affected_contract_count", "excluded_observation_count",
    "quality_warnings", "created_at",
]


def _insert(table: str, columns: list[str], rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if rows:
        c = _ensure_client(client)
        c.insert(table, [tuple(row.get(name) for name in columns) for row in rows], column_names=columns)


def insert_universe(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    _insert(UNIVERSE_TABLE, UNIVERSE_COLUMNS, rows, client)


def insert_fits(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    _insert(FITS_TABLE, FIT_COLUMNS, rows, client)


def insert_observations(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    _insert(OBSERVATIONS_TABLE, OBSERVATION_COLUMNS, rows, client)


def insert_rankings(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    _insert(RANKINGS_TABLE, RANKING_COLUMNS, rows, client)


def get_frozen_universe(run_id: str, client: Client | None = None) -> list[dict[str, Any]]:
    c = _ensure_client(client)
    result = c.query(
        f"SELECT * FROM `{UNIVERSE_TABLE}` FINAL WHERE run_id = {{rid:UUID}} "
        "ORDER BY underlying_instrument_code, expiry_date, strike, option_type",
        parameters={"rid": run_id},
    )
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def _where(**filters: Any) -> tuple[str, dict[str, Any]]:
    definitions = {
        "run_id": ("rid", "UUID"), "underlying_instrument_code": ("underlying", "String"),
        "expiry_date": ("expiry", "Date"), "option_type": ("option_type", "String"),
        "snapshot_time": ("snapshot", "DateTime64(3, 'Asia/Tehran')"),
        "quality_status": ("quality", "String"),
    }
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for column, value in filters.items():
        if value is None or column not in definitions:
            continue
        if column == "quality_status" and value == "eligible":
            clauses.append("quality_status IN ('valid', 'warning')")
            continue
        parameter, ch_type = definitions[column]
        clauses.append(f"{column} = {{{parameter}:{ch_type}}}")
        params[parameter] = value
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def _rows(result) -> list[dict[str, Any]]:
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def _sanitize_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep legacy invalid rows diagnostic-only even if they predate this rule."""
    distance_fields = (
        "bid_distance", "ask_distance", "midpoint_distance",
        "bid_distance_bps", "ask_distance_bps", "midpoint_distance_bps",
    )
    for row in rows:
        if row.get("quality_status") == "invalid":
            for field in distance_fields:
                if field in row:
                    row[field] = None
    return rows


async def get_rankings(run_id: str, sort_by: str = "p90", limit: int = 1000) -> list[dict[str, Any]]:
    orders = {
        "p90": "p90_abs_midpoint_bps", "median": "median_abs_midpoint_bps",
        "largest": "greatest(abs(largest_bid_deviation_bps), abs(largest_ask_deviation_bps))",
        "affected_contracts": "affected_contract_count",
    }
    client = await get_async_client()
    result = await client.query(
        f"SELECT * FROM `{RANKINGS_TABLE}` FINAL WHERE run_id = {{rid:UUID}} "
        f"ORDER BY {orders.get(sort_by, orders['p90'])} DESC LIMIT {{lim:UInt32}}",
        parameters={"rid": run_id, "lim": limit},
    )
    return _rows(result)


async def get_snapshot_summaries(run_id: str, underlying: str, expiry: date | None = None) -> list[dict[str, Any]]:
    where, params = _where(run_id=run_id, underlying_instrument_code=underlying, expiry_date=expiry)
    client = await get_async_client()
    result = await client.query(
        f"SELECT snapshot_time, expiry_date, count() observation_count, "
        "countIf(quality_status IN ('valid','warning')) valid_count, "
        "countIf(quality_status = 'invalid') invalid_count, "
        "quantileExactIf(0.5)(abs(midpoint_distance_bps), quality_status IN ('valid','warning')) median_abs_midpoint_bps, "
        "quantileExactIf(0.9)(abs(midpoint_distance_bps), quality_status IN ('valid','warning')) p90_abs_midpoint_bps "
        f"FROM `{OBSERVATIONS_TABLE}` {where} GROUP BY snapshot_time, expiry_date "
        "ORDER BY expiry_date, snapshot_time",
        parameters=params,
    )
    return _rows(result)


async def get_observations(
    *, run_id: str, underlying_instrument_code: str | None = None, expiry_date: date | None = None,
    option_type: str | None = None, snapshot_time: datetime | None = None,
    quality_status: str | None = None, minimum_absolute_distance_bps: float | None = None,
    offset: int = 0, limit: int = 100,
) -> list[dict[str, Any]]:
    where, params = _where(
        run_id=run_id, underlying_instrument_code=underlying_instrument_code, expiry_date=expiry_date,
        option_type=option_type, snapshot_time=snapshot_time, quality_status=quality_status,
    )
    if minimum_absolute_distance_bps is not None:
        if quality_status is None:
            where += (" AND " if where else "WHERE ") + "quality_status IN ('valid', 'warning')"
        where += (" AND " if where else "WHERE ") + "abs(midpoint_distance_bps) >= {min_distance:Float64}"
        params["min_distance"] = minimum_absolute_distance_bps
    params.update(lim=limit, off=offset)
    client = await get_async_client()
    result = await client.query(
        f"SELECT * FROM `{OBSERVATIONS_TABLE}` {where} "
        "ORDER BY snapshot_time DESC, expiry_date, strike, option_type, instrument_code "
        "LIMIT {lim:UInt32} OFFSET {off:UInt32}", parameters=params,
    )
    return _sanitize_observations(_rows(result))


async def count_observations(**filters: Any) -> int:
    offset = filters.pop("offset", None); limit = filters.pop("limit", None)
    where, params = _where(**{key: value for key, value in filters.items() if key != "minimum_absolute_distance_bps"})
    minimum = filters.get("minimum_absolute_distance_bps")
    if minimum is not None:
        if filters.get("quality_status") is None:
            where += (" AND " if where else "WHERE ") + "quality_status IN ('valid', 'warning')"
        where += (" AND " if where else "WHERE ") + "abs(midpoint_distance_bps) >= {min_distance:Float64}"
        params["min_distance"] = minimum
    client = await get_async_client()
    result = await client.query(f"SELECT count() FROM `{OBSERVATIONS_TABLE}` {where}", parameters=params)
    return int(result.result_rows[0][0]) if result.result_rows else 0


async def get_fits(
    run_id: str, underlying_instrument_code: str | None = None, expiry_date: date | None = None,
    snapshot_time: datetime | None = None, quality_status: str | None = None, limit: int = 10000,
) -> list[dict[str, Any]]:
    where, params = _where(
        run_id=run_id, underlying_instrument_code=underlying_instrument_code,
        expiry_date=expiry_date, snapshot_time=snapshot_time, quality_status=quality_status,
    )
    params["lim"] = limit
    client = await get_async_client()
    result = await client.query(
        f"SELECT * FROM `{FITS_TABLE}` {where} ORDER BY snapshot_time DESC, expiry_date LIMIT {{lim:UInt32}}",
        parameters=params,
    )
    return _rows(result)
