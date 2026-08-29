from datetime import date
from typing import Any

from src.db.clickhouse import get_async_client, price_from_storage
from src.db.clickhouse.schema import (
    ensure_tables,
    GOLD_ORDER_BOOK_TABLE,
    GOLD_TRADES_TABLE,
    GOLD_ORDER_BOOK_COLUMNS,
    GOLD_TRADES_COLUMNS,
    run_migrations,
    downgrade_migration,
    migration_history,
    migration_pending,
    migration_check,
)
from src.db.clickhouse.insert import insert_gold_order_book, insert_gold_trades


def _row_to_dict_gld_ob(row: tuple[Any, ...]) -> dict[str, Any]:
    d = dict(zip(GOLD_ORDER_BOOK_COLUMNS, row))
    d["bid_price"] = price_from_storage(d["bid_price"])
    d["ask_price"] = price_from_storage(d["ask_price"])
    return d


def _row_to_dict_gld_tr(row: tuple[Any, ...]) -> dict[str, Any]:
    d = dict(zip(GOLD_TRADES_COLUMNS, row))
    d["price"] = price_from_storage(d["price"])
    d["value"] = price_from_storage(d["value"])
    return d


async def get_gold_latest_order_book(instrument_code: str, trade_date: date) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT * FROM `{GOLD_ORDER_BOOK_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} AND trade_date = {{dt:Date}} "
        f"ORDER BY trade_time DESC, depth_level ASC LIMIT 5"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date})).result_rows
    return [_row_to_dict_gld_ob(r) for r in rows]


async def get_gold_order_book_history(instrument_code: str, trade_date: date) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT * FROM `{GOLD_ORDER_BOOK_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} AND trade_date = {{dt:Date}} "
        f"ORDER BY trade_time ASC, depth_level ASC"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date})).result_rows
    return [_row_to_dict_gld_ob(r) for r in rows]


async def get_gold_trades_intraday(
    instrument_code: str,
    trade_date: date,
    from_time: int | None = None,
    to_time: int | None = None,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    conditions = ["instrument_code = {code:String}", "trade_date = {dt:Date}"]
    params: dict[str, Any] = {"code": instrument_code, "dt": trade_date, "lim": limit}
    if from_time is not None:
        conditions.append("trade_time >= {from_time:UInt32}")
        params["from_time"] = from_time
    if to_time is not None:
        conditions.append("trade_time <= {to_time:UInt32}")
        params["to_time"] = to_time
    where = " AND ".join(conditions)
    q = f"SELECT * FROM `{GOLD_TRADES_TABLE}` FINAL WHERE {where} ORDER BY trade_time ASC, trade_id ASC LIMIT {{lim:UInt32}}"
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_gld_tr(r) for r in rows]


async def get_gold_trades_daily(instrument_code: str, from_date: date, to_date: date) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT trade_date, count() as trades_count, sum(volume) as total_volume, "
        f"sum(value) as total_value, min(price) as low_price, max(price) as high_price "
        f"FROM `{GOLD_TRADES_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} AND trade_date >= {{frm:Date}} AND trade_date <= {{to:Date}} "
        f"GROUP BY trade_date ORDER BY trade_date ASC"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "frm": from_date, "to": to_date})).result_rows
    cols = ["trade_date", "trades_count", "total_volume", "total_value", "low_price", "high_price"]
    res = []
    for r in rows:
        d = dict(zip(cols, r))
        d["low_price"] = price_from_storage(d["low_price"])
        d["high_price"] = price_from_storage(d["high_price"])
        d["total_value"] = price_from_storage(d["total_value"])
        res.append(d)
    return res


async def get_gold_vwap(instrument_code: str, trade_date: date) -> dict[str, Any] | None:
    client = await get_async_client()
    q = (
        f"SELECT sum(value) as total_value, sum(volume) as total_volume "
        f"FROM `{GOLD_TRADES_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} AND trade_date = {{dt:Date}}"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date})).result_rows
    if not rows or not rows[0][1]:
        return None
    tot_val, tot_vol = rows[0]
    return {
        "vwap": price_from_storage(tot_val) / tot_vol if tot_vol else 0.0,
        "total_volume": tot_vol,
        "total_value": price_from_storage(tot_val),
    }


async def get_gold_ohlcv(instrument_code: str, trade_date: date) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT toStartOfMinute(toDateTime(trade_date) + trade_time) as time_bucket, "
        f"argMin(price, trade_time) as open, max(price) as high, min(price) as low, "
        f"argMax(price, trade_time) as close, sum(volume) as volume "
        f"FROM `{GOLD_TRADES_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} AND trade_date = {{dt:Date}} "
        f"GROUP BY time_bucket ORDER BY time_bucket ASC"
    )
    rows = (await client.query(q, parameters={"code": instrument_code, "dt": trade_date})).result_rows
    res = []
    for r in rows:
        res.append({
            "time": r[0],
            "open": price_from_storage(r[1]),
            "high": price_from_storage(r[2]),
            "low": price_from_storage(r[3]),
            "close": price_from_storage(r[4]),
            "volume": r[5],
        })
    return res


async def count_gold_order_book(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    depth_level: int | None = None,
    data_source: str | None = None,
) -> int:
    client = await get_async_client()
    conditions = []
    params: dict[str, Any] = {}
    if instrument_code:
        conditions.append("instrument_code = {code:String}")
        params["code"] = instrument_code
    if trade_date:
        conditions.append("trade_date = {dt:Date}")
        params["dt"] = trade_date
    if depth_level:
        conditions.append("depth_level = {depth:UInt8}")
        params["depth"] = depth_level
    if data_source:
        conditions.append("data_source = {src:String}")
        params["src"] = data_source
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    q = f"SELECT count() FROM `{GOLD_ORDER_BOOK_TABLE}` FINAL {where}"
    rows = (await client.query(q, parameters=params)).result_rows
    return int(rows[0][0]) if rows else 0


async def get_gold_order_book_paginated(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    depth_level: int | None = None,
    data_source: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    conditions = []
    params: dict[str, Any] = {"lim": limit, "off": offset}
    if instrument_code:
        conditions.append("instrument_code = {code:String}")
        params["code"] = instrument_code
    if trade_date:
        conditions.append("trade_date = {dt:Date}")
        params["dt"] = trade_date
    if depth_level:
        conditions.append("depth_level = {depth:UInt8}")
        params["depth"] = depth_level
    if data_source:
        conditions.append("data_source = {src:String}")
        params["src"] = data_source
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    q = (
        f"SELECT * FROM `{GOLD_ORDER_BOOK_TABLE}` FINAL {where} "
        f"ORDER BY trade_date DESC, trade_time DESC, depth_level ASC "
        f"LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_gld_ob(r) for r in rows]


async def count_gold_trades(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    is_canceled: int | None = None,
    data_source: str | None = None,
) -> int:
    client = await get_async_client()
    conditions = []
    params: dict[str, Any] = {}
    if instrument_code:
        conditions.append("instrument_code = {code:String}")
        params["code"] = instrument_code
    if trade_date:
        conditions.append("trade_date = {dt:Date}")
        params["dt"] = trade_date
    if min_price is not None:
        conditions.append("price >= {min_p:Int64}")
        params["min_p"] = min_price
    if max_price is not None:
        conditions.append("price <= {max_p:Int64}")
        params["max_p"] = max_price
    if is_canceled is not None:
        conditions.append("is_canceled = {cxl:UInt8}")
        params["cxl"] = is_canceled
    if data_source:
        conditions.append("data_source = {src:String}")
        params["src"] = data_source
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    q = f"SELECT count() FROM `{GOLD_TRADES_TABLE}` FINAL {where}"
    rows = (await client.query(q, parameters=params)).result_rows
    return int(rows[0][0]) if rows else 0


async def get_gold_trades_paginated(
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
    conditions = []
    params: dict[str, Any] = {"lim": limit, "off": offset}
    if instrument_code:
        conditions.append("instrument_code = {code:String}")
        params["code"] = instrument_code
    if trade_date:
        conditions.append("trade_date = {dt:Date}")
        params["dt"] = trade_date
    if min_price is not None:
        conditions.append("price >= {min_p:Int64}")
        params["min_p"] = min_price
    if max_price is not None:
        conditions.append("price <= {max_p:Int64}")
        params["max_p"] = max_price
    if is_canceled is not None:
        conditions.append("is_canceled = {cxl:UInt8}")
        params["cxl"] = is_canceled
    if data_source:
        conditions.append("data_source = {src:String}")
        params["src"] = data_source
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    q = (
        f"SELECT * FROM `{GOLD_TRADES_TABLE}` FINAL {where} "
        f"ORDER BY trade_date DESC, trade_time DESC "
        f"LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_gld_tr(r) for r in rows]


__all__ = [
    "ensure_tables",
    "run_migrations",
    "downgrade_migration",
    "migration_history",
    "migration_pending",
    "migration_check",
    "GOLD_ORDER_BOOK_TABLE",
    "GOLD_TRADES_TABLE",
    "GOLD_ORDER_BOOK_COLUMNS",
    "GOLD_TRADES_COLUMNS",
    "insert_gold_order_book",
    "insert_gold_trades",
    "get_gold_latest_order_book",
    "get_gold_order_book_history",
    "get_gold_trades_intraday",
    "get_gold_trades_daily",
    "get_gold_vwap",
    "get_gold_ohlcv",
    "count_gold_order_book",
    "get_gold_order_book_paginated",
    "count_gold_trades",
    "get_gold_trades_paginated",
]
