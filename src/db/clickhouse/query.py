from datetime import date
from typing import Any

from src.db.clickhouse import get_async_client, price_from_storage
from src.db.clickhouse.schema import (
    ORDER_BOOK_TABLE,
    ORDER_BOOK_COLUMNS,
    TRADES_TABLE,
    TRADES_COLUMNS,
    YIELD_CURVE_FITS_TABLE,
    YIELD_CURVE_FITS_COLUMNS,
    YIELD_CURVE_BONDS_TABLE,
    YIELD_CURVE_BONDS_COLUMNS,
)

_OB_COLUMNS = ORDER_BOOK_COLUMNS
_TR_COLUMNS = TRADES_COLUMNS
_YC_FITS_COLUMNS = YIELD_CURVE_FITS_COLUMNS
_YC_BONDS_COLUMNS = YIELD_CURVE_BONDS_COLUMNS


def _build_where(specs: list[tuple]) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for spec in specs:
        column, param_name, ch_type, value = spec[:4]
        op = spec[4] if len(spec) > 4 else "="
        if value is None:
            continue
        clauses.append(f"{column} {op} {{{param_name}:{ch_type}}}")
        params[param_name] = value
    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)
    return where, params


def _ob_filters(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    depth_level: int | None = None,
    data_source: str | None = None,
) -> list[tuple]:
    specs: list[tuple] = []
    if instrument_code:
        specs.append(("instrument_code", "code", "String", instrument_code))
    if trade_date:
        specs.append(("trade_date", "dt", "Date", trade_date))
    if depth_level is not None:
        specs.append(("depth_level", "dl", "UInt8", depth_level))
    if data_source:
        specs.append(("data_source", "ds", "String", data_source))
    return specs


def _tr_filters(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    is_canceled: int | None = None,
    data_source: str | None = None,
) -> list[tuple]:
    specs: list[tuple] = []
    if instrument_code:
        specs.append(("instrument_code", "code", "String", instrument_code))
    if trade_date:
        specs.append(("trade_date", "dt", "Date", trade_date))
    if min_price is not None:
        specs.append(("price", "minp", "Int64", min_price, ">="))
    if max_price is not None:
        specs.append(("price", "maxp", "Int64", max_price, "<="))
    if is_canceled is not None:
        specs.append(("is_canceled", "ic", "UInt8", is_canceled))
    if data_source:
        specs.append(("data_source", "ds", "String", data_source))
    return specs


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
    specs = _ob_filters(instrument_code, trade_date, depth_level, data_source)
    where, params = _build_where(specs)
    params["lim"] = limit
    params["off"] = offset
    q = (
        f"SELECT * FROM `{ORDER_BOOK_TABLE}` FINAL {where} "
        f"ORDER BY trade_date DESC, trade_time DESC, depth_level ASC "
        f"LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_ob(r) for r in rows]


async def count_order_book(
    instrument_code: str | None = None,
    trade_date: date | None = None,
    depth_level: int | None = None,
    data_source: str | None = None,
) -> int:
    client = await get_async_client()
    specs = _ob_filters(instrument_code, trade_date, depth_level, data_source)
    where, params = _build_where(specs)
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
    specs = _tr_filters(instrument_code, trade_date, min_price, max_price, is_canceled, data_source)
    where, params = _build_where(specs)
    params["lim"] = limit
    params["off"] = offset
    q = (
        f"SELECT * FROM `{TRADES_TABLE}` FINAL {where} "
        f"ORDER BY trade_date DESC, trade_time DESC "
        f"LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}"
    )
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
    specs = _tr_filters(instrument_code, trade_date, min_price, max_price, is_canceled, data_source)
    where, params = _build_where(specs)
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


def _row_to_dict_ycf(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(_YC_FITS_COLUMNS, row))


def _row_to_dict_ycb(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(_YC_BONDS_COLUMNS, row))


def _ycf_filters(
    trade_date: date | None = None,
    curve_side: str | None = None,
    converged: int | None = None,
) -> list[tuple]:
    specs: list[tuple] = []
    if trade_date is not None:
        specs.append(("trade_date", "dt", "Date", trade_date))
    if curve_side not in (None, "", "both"):
        specs.append(("curve_side", "side", "String", curve_side))
    if converged is not None:
        specs.append(("converged", "conv", "UInt8", converged))
    return specs


def _ycb_filters(
    trade_date: date | None = None,
    trade_time: int | None = None,
    instrument_code: str | None = None,
    curve_side: str | None = None,
    symbol: str | None = None,
) -> list[tuple]:
    specs: list[tuple] = []
    if trade_date is not None:
        specs.append(("trade_date", "dt", "Date", trade_date))
    if trade_time is not None:
        specs.append(("trade_time", "tt", "UInt32", trade_time))
    if instrument_code:
        specs.append(("instrument_code", "code", "String", instrument_code))
    if curve_side not in (None, "", "both"):
        specs.append(("curve_side", "side", "String", curve_side))
    if symbol:
        specs.append(("symbol", "sym", "String", symbol))
    return specs


async def get_yield_curve_fits(
    trade_date: date,
    curve_side: str | None = None,
    from_time: int | None = None,
    to_time: int | None = None,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where_clauses = ["trade_date = {dt:Date}"]
    params: dict[str, Any] = {"dt": trade_date}

    if curve_side and curve_side != "both":
        where_clauses.append("curve_side = {side:String}")
        params["side"] = curve_side
    if from_time is not None:
        where_clauses.append("trade_time >= {ft:UInt32}")
        params["ft"] = from_time
    if to_time is not None:
        where_clauses.append("trade_time <= {tt:UInt32}")
        params["tt"] = to_time

    where = " AND ".join(where_clauses)
    cols = ", ".join(f"`{c}`" for c in _YC_FITS_COLUMNS)
    q = (
        f"SELECT {cols} FROM ("
        f"  SELECT {cols} FROM `{YIELD_CURVE_FITS_TABLE}` "
        f"  WHERE {where} "
        f"  ORDER BY computed_at DESC "
        f"  LIMIT 1 BY trade_date, trade_time, curve_side"
        f") ORDER BY trade_time ASC, curve_side ASC"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_ycf(r) for r in rows]


async def get_latest_yield_curve(
    curve_side: str | None = None,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where = ""
    params: dict[str, Any] = {}
    if curve_side and curve_side != "both":
        where = "WHERE curve_side = {side:String}"
        params["side"] = curve_side

    cols = ", ".join(f"`{c}`" for c in _YC_FITS_COLUMNS)
    q = (
        f"SELECT {cols} FROM ("
        f"  SELECT {cols} FROM `{YIELD_CURVE_FITS_TABLE}` {where} "
        f"  ORDER BY computed_at DESC "
        f"  LIMIT 1 BY curve_side"
        f") ORDER BY curve_side ASC"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_ycf(r) for r in rows]


async def get_yield_curve_bonds(
    trade_date: date,
    trade_time: int,
    curve_side: str | None = None,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where_clauses = ["trade_date = {dt:Date}", "trade_time = {tt:UInt32}"]
    params: dict[str, Any] = {"dt": trade_date, "tt": trade_time}

    if curve_side and curve_side != "both":
        where_clauses.append("curve_side = {side:String}")
        params["side"] = curve_side

    where = " AND ".join(where_clauses)
    cols = ", ".join(f"`{c}`" for c in _YC_BONDS_COLUMNS)
    q = (
        f"SELECT {cols} FROM ("
        f"  SELECT {cols} FROM `{YIELD_CURVE_BONDS_TABLE}` "
        f"  WHERE {where} "
        f"  ORDER BY computed_at DESC "
        f"  LIMIT 1 BY instrument_code, trade_date, trade_time, curve_side"
        f") ORDER BY instrument_code ASC, curve_side ASC"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_ycb(r) for r in rows]


async def get_yield_spread_intraday(
    instrument_code: str,
    trade_date: date,
    curve_side: str | None = None,
    from_time: int | None = None,
    to_time: int | None = None,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where_clauses = [
        "instrument_code = {code:String}",
        "trade_date = {dt:Date}",
        "spread_bps IS NOT NULL",
    ]
    params: dict[str, Any] = {"code": instrument_code, "dt": trade_date}

    if curve_side and curve_side != "both":
        where_clauses.append("curve_side = {side:String}")
        params["side"] = curve_side
    if from_time is not None:
        where_clauses.append("trade_time >= {ft:UInt32}")
        params["ft"] = from_time
    if to_time is not None:
        where_clauses.append("trade_time <= {tt:UInt32}")
        params["tt"] = to_time

    where = " AND ".join(where_clauses)
    q = (
        f"SELECT trade_time, curve_side, spread_bps "
        f"FROM `{YIELD_CURVE_BONDS_TABLE}` FINAL "
        f"WHERE {where} "
        f"ORDER BY trade_time ASC, curve_side ASC"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    result: list[dict[str, Any]] = []
    for r in rows:
        result.append({
            "trade_time": int(r[0]),
            "curve_side": r[1],
            "spread_bps": float(r[2]) if r[2] is not None else None,
        })
    return result


async def get_yield_spread_daily(
    instrument_code: str,
    from_date: date,
    to_date: date,
    curve_side: str | None = None,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where_clauses = [
        "instrument_code = {code:String}",
        "trade_date BETWEEN {fd:Date} AND {td:Date}",
        "spread_bps IS NOT NULL",
    ]
    params: dict[str, Any] = {
        "code": instrument_code,
        "fd": from_date,
        "td": to_date,
    }

    if curve_side and curve_side != "both":
        where_clauses.append("curve_side = {side:String}")
        params["side"] = curve_side

    where = " AND ".join(where_clauses)
    q = (
        f"SELECT trade_date, curve_side, spread_bps "
        f"FROM `{YIELD_CURVE_BONDS_TABLE}` FINAL "
        f"WHERE {where} "
        f"ORDER BY trade_date ASC, curve_side ASC"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    result: list[dict[str, Any]] = []
    for r in rows:
        result.append({
            "trade_date": r[0],
            "curve_side": r[1],
            "spread_bps": float(r[2]) if r[2] is not None else None,
        })
    return result


async def get_yield_curve_fits_paginated(
    trade_date: date | None = None,
    curve_side: str | None = None,
    converged: int | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    specs = _ycf_filters(trade_date, curve_side, converged)
    where, params = _build_where(specs)
    params["lim"] = limit
    params["off"] = offset
    q = (
        f"SELECT * FROM `{YIELD_CURVE_FITS_TABLE}` FINAL {where} "
        f"ORDER BY trade_date DESC, trade_time DESC, curve_side ASC "
        f"LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_ycf(r) for r in rows]


async def count_yield_curve_fits(
    trade_date: date | None = None,
    curve_side: str | None = None,
    converged: int | None = None,
) -> int:
    client = await get_async_client()
    specs = _ycf_filters(trade_date, curve_side, converged)
    where, params = _build_where(specs)
    q = f"SELECT count() FROM `{YIELD_CURVE_FITS_TABLE}` FINAL {where}"
    rows = (await client.query(q, parameters=params)).result_rows
    return int(rows[0][0]) if rows else 0


async def get_yield_curve_bonds_paginated(
    trade_date: date | None = None,
    trade_time: int | None = None,
    instrument_code: str | None = None,
    curve_side: str | None = None,
    symbol: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    specs = _ycb_filters(trade_date, trade_time, instrument_code, curve_side, symbol)
    where, params = _build_where(specs)
    params["lim"] = limit
    params["off"] = offset
    q = (
        f"SELECT * FROM `{YIELD_CURVE_BONDS_TABLE}` FINAL {where} "
        f"ORDER BY trade_date DESC, trade_time DESC, instrument_code ASC, curve_side ASC "
        f"LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    return [_row_to_dict_ycb(r) for r in rows]


async def count_yield_curve_bonds(
    trade_date: date | None = None,
    trade_time: int | None = None,
    instrument_code: str | None = None,
    curve_side: str | None = None,
    symbol: str | None = None,
) -> int:
    client = await get_async_client()
    specs = _ycb_filters(trade_date, trade_time, instrument_code, curve_side, symbol)
    where, params = _build_where(specs)
    q = f"SELECT count() FROM `{YIELD_CURVE_BONDS_TABLE}` FINAL {where}"
    rows = (await client.query(q, parameters=params)).result_rows
    return int(rows[0][0]) if rows else 0


async def get_bond_trades_intraday(
    instrument_code: str,
    trade_date: date,
    from_time: int | None = None,
    to_time: int | None = None,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where_clauses = [
        "instrument_code = {code:String}",
        "trade_date = {dt:Date}",
        "is_canceled = 0",
    ]
    params: dict[str, Any] = {"code": instrument_code, "dt": trade_date, "lim": limit}
    if from_time is not None:
        where_clauses.append("trade_time >= {ft:UInt32}")
        params["ft"] = from_time
    if to_time is not None:
        where_clauses.append("trade_time <= {tt:UInt32}")
        params["tt"] = to_time
    where = " AND ".join(where_clauses)
    q = (
        f"SELECT trade_time, price, value "
        f"FROM `{TRADES_TABLE}` FINAL "
        f"WHERE {where} "
        f"ORDER BY trade_time ASC, trade_id ASC "
        f"LIMIT {{lim:UInt32}}"
    )
    rows = (await client.query(q, parameters=params)).result_rows
    result: list[dict[str, Any]] = []
    for r in rows:
        result.append({
            "trade_time": int(r[0]),
            "price": price_from_storage(int(r[1])),
            "value": price_from_storage(int(r[2])),
        })
    return result


async def get_bond_trades_daily(
    instrument_code: str,
    from_date: date,
    to_date: date,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    q = (
        f"SELECT trade_date, sum(value) AS val "
        f"FROM `{TRADES_TABLE}` FINAL "
        f"WHERE instrument_code = {{code:String}} "
        f"  AND trade_date BETWEEN {{fd:Date}} AND {{td:Date}} "
        f"  AND is_canceled = 0 "
        f"GROUP BY trade_date "
        f"ORDER BY trade_date ASC"
    )
    params = {"code": instrument_code, "fd": from_date, "td": to_date}
    rows = (await client.query(q, parameters=params)).result_rows
    return [{"trade_date": r[0], "value": price_from_storage(int(r[1]))} for r in rows]
