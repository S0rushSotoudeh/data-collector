from datetime import date
from typing import Any

from src.db.clickhouse import get_async_client, price_from_storage
from src.db.clickhouse.schema import ORDER_BOOK_TABLE, ORDER_BOOK_COLUMNS, TRADES_TABLE, TRADES_COLUMNS

_OB_COLUMNS = ORDER_BOOK_COLUMNS
_TR_COLUMNS = TRADES_COLUMNS


async def get_latest_order_book(
    instrument_code: str,
    trade_date: date,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT * FROM `{ORDER_BOOK_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} AND trade_date = {{dt:Date}} "
        f"ORDER BY trade_time DESC, depth_level ASC "
        f"LIMIT 5"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date})).result_rows
    return [_row_to_dict_ob(r) for r in rows]


async def get_order_book_history(
    instrument_code: str,
    trade_date: date,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT * FROM `{ORDER_BOOK_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} AND trade_date = {{dt:Date}} "
        f"ORDER BY trade_time ASC, depth_level ASC"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date})).result_rows
    return [_row_to_dict_ob(r) for r in rows]


async def get_latest_order_books(
    limit: int = 10,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT * FROM `{ORDER_BOOK_TABLE}` FINAL "
        f"ORDER BY ingested_at DESC "
        f"LIMIT {{lim:UInt16}}"
    )
    rows = (await client.query(q, parameters={"lim": limit})).result_rows
    return [_row_to_dict_ob(r) for r in rows]


async def get_trade_history(
    instrument_code: str,
    trade_date: date,
    limit: int = 500,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT * FROM `{TRADES_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} AND trade_date = {{dt:Date}} "
        f"ORDER BY trade_time ASC "
        f"LIMIT {{lim:UInt16}}"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date, "lim": limit})).result_rows
    return [_row_to_dict_tr(r) for r in rows]


async def get_vwap(
    instrument_code: str,
    trade_date: date,
) -> dict[str, Any] | None:
    client = await get_async_client()
    q = (
        f"SELECT "
        f"    toFloat64(sum(value)) / toFloat64(sum(volume)) AS vwap, "
        f"    sum(volume) AS total_volume, "
        f"    sum(value) AS total_value, "
        f"    count() AS trade_count "
        f"FROM `{TRADES_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} "
        f"  AND trade_date = {{dt:Date}} "
        f"  AND is_canceled = 0"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date})).result_rows
    if not rows or rows[0][0] is None:
        return None
    return {
        "vwap": price_from_storage(int(rows[0][0])),
        "total_volume": int(rows[0][1]),
        "total_value": price_from_storage(int(rows[0][2])),
        "trade_count": int(rows[0][3]),
    }


async def get_ohlcv(
    instrument_code: str,
    trade_date: date,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT "
        f"    toHour(trade_time) AS hour, "
        f"    argMin(price, trade_time) AS open, "
        f"    max(price) AS high, "
        f"    min(price) AS low, "
        f"    argMax(price, trade_time) AS close, "
        f"    sum(volume) AS volume, "
        f"    toFloat64(sum(value)) / toFloat64(sum(volume)) AS vwap "
        f"FROM `{TRADES_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} "
        f"  AND trade_date = {{dt:Date}} "
        f"  AND is_canceled = 0 "
        f"GROUP BY hour "
        f"ORDER BY hour ASC"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date})).result_rows
    result: list[dict[str, Any]] = []
    for r in rows:
        result.append({
            "hour": int(r[0]),
            "open": price_from_storage(int(r[1])),
            "high": price_from_storage(int(r[2])),
            "low": price_from_storage(int(r[3])),
            "close": price_from_storage(int(r[4])),
            "volume": int(r[5]),
            "vwap": price_from_storage(int(r[6])),
        })
    return result


async def get_daily_spread(
    instrument_code: str,
    trade_date: date,
) -> dict[str, Any] | None:
    client = await get_async_client()
    q = (
        f"SELECT "
        f"    min(ask_price - bid_price) AS min_spread, "
        f"    max(ask_price - bid_price) AS max_spread, "
        f"    avg(ask_price - bid_price) AS avg_spread "
        f"FROM `{ORDER_BOOK_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} "
        f"  AND trade_date = {{dt:Date}} "
        f"  AND depth_level = 1 "
        f"  AND bid_price > 0 AND ask_price > 0"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date})).result_rows
    if not rows or rows[0][0] is None:
        return None
    return {
        "min_spread": float(rows[0][0]),
        "max_spread": float(rows[0][1]),
        "avg_spread": float(rows[0][2]),
    }


async def get_latest_trades(
    limit: int = 10,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT * FROM `{TRADES_TABLE}` FINAL "
        f"WHERE trade_date >= today() - 1 "
        f"ORDER BY trade_date DESC, trade_time DESC "
        f"LIMIT {{lim:UInt16}}"
    )
    rows = (await client.query(q, parameters={"lim": limit})).result_rows
    return [_row_to_dict_tr(r) for r in rows]


async def get_order_book_paginated(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    depth_level: int | None = None,
    data_source: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if instrument_code:
        where_clauses.append("instrument_code = {code:String}")
        params["code"] = instrument_code
    if trade_date:
        where_clauses.append("trade_date = {dt:Date}")
        params["dt"] = trade_date
    if depth_level is not None:
        where_clauses.append("depth_level = {dl:UInt8}")
        params["dl"] = depth_level
    if data_source:
        where_clauses.append("data_source = {ds:String}")
        params["ds"] = data_source

    where = ""
    if where_clauses:
        where = "WHERE " + " AND ".join(where_clauses)

    q = (
        f"SELECT * FROM `{ORDER_BOOK_TABLE}` FINAL {where} "
        f"ORDER BY trade_date DESC, trade_time DESC, depth_level ASC "
        f"LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}"
    )
    params["lim"] = limit
    params["off"] = offset
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_ob(r) for r in rows]


async def count_order_book(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    depth_level: int | None = None,
    data_source: str | None = None,
) -> int:
    client = await get_async_client()
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if instrument_code:
        where_clauses.append("instrument_code = {code:String}")
        params["code"] = instrument_code
    if trade_date:
        where_clauses.append("trade_date = {dt:Date}")
        params["dt"] = trade_date
    if depth_level is not None:
        where_clauses.append("depth_level = {dl:UInt8}")
        params["dl"] = depth_level
    if data_source:
        where_clauses.append("data_source = {ds:String}")
        params["ds"] = data_source

    where = ""
    if where_clauses:
        where = "WHERE " + " AND ".join(where_clauses)

    q = f"SELECT count() FROM `{ORDER_BOOK_TABLE}` FINAL {where}"
    rows = (await client.query(q, parameters=params)).result_rows
    return int(rows[0][0]) if rows else 0


async def get_trades_paginated(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    is_canceled: int | None = None,
    data_source: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if instrument_code:
        where_clauses.append("instrument_code = {code:String}")
        params["code"] = instrument_code
    if trade_date:
        where_clauses.append("trade_date = {dt:Date}")
        params["dt"] = trade_date
    if min_price is not None:
        where_clauses.append("price >= {minp:Int64}")
        params["minp"] = min_price
    if max_price is not None:
        where_clauses.append("price <= {maxp:Int64}")
        params["maxp"] = max_price
    if is_canceled is not None:
        where_clauses.append("is_canceled = {ic:UInt8}")
        params["ic"] = is_canceled
    if data_source:
        where_clauses.append("data_source = {ds:String}")
        params["ds"] = data_source

    where = ""
    if where_clauses:
        where = "WHERE " + " AND ".join(where_clauses)

    q = (
        f"SELECT * FROM `{TRADES_TABLE}` FINAL {where} "
        f"ORDER BY trade_date DESC, trade_time DESC "
        f"LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}"
    )
    params["lim"] = limit
    params["off"] = offset
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_tr(r) for r in rows]


async def count_trades(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    is_canceled: int | None = None,
    data_source: str | None = None,
) -> int:
    client = await get_async_client()
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if instrument_code:
        where_clauses.append("instrument_code = {code:String}")
        params["code"] = instrument_code
    if trade_date:
        where_clauses.append("trade_date = {dt:Date}")
        params["dt"] = trade_date
    if min_price is not None:
        where_clauses.append("price >= {minp:Int64}")
        params["minp"] = min_price
    if max_price is not None:
        where_clauses.append("price <= {maxp:Int64}")
        params["maxp"] = max_price
    if is_canceled is not None:
        where_clauses.append("is_canceled = {ic:UInt8}")
        params["ic"] = is_canceled
    if data_source:
        where_clauses.append("data_source = {ds:String}")
        params["ds"] = data_source

    where = ""
    if where_clauses:
        where = "WHERE " + " AND ".join(where_clauses)

    q = f"SELECT count() FROM `{TRADES_TABLE}` FINAL {where}"
    rows = (await client.query(q, parameters=params)).result_rows
    return int(rows[0][0]) if rows else 0


def _row_to_dict_ob(row: tuple[Any, ...]) -> dict[str, Any]:
    d = dict(zip(_OB_COLUMNS, row))
    d["bid_price"] = price_from_storage(d["bid_price"])
    d["ask_price"] = price_from_storage(d["ask_price"])
    return d


def _row_to_dict_tr(row: tuple[Any, ...]) -> dict[str, Any]:
    d = dict(zip(_TR_COLUMNS, row))
    d["price"] = price_from_storage(d["price"])
    d["value"] = price_from_storage(d["value"])
    return d