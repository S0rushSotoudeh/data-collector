"""Date-scoped, count-free browsing for the high-volume admin tables."""

from datetime import date
from typing import Any

from src.db.clickhouse import get_async_client
from src.db.clickhouse.query import (
    _build_where, _ob_filters, _tr_filters,
    _row_to_dict_ob, _row_to_dict_tr,
    _row_to_dict_opt_ob, _row_to_dict_opt_tr,
    _row_to_dict_stk_ob, _row_to_dict_stk_tr,
)
from src.db.clickhouse.schema import (
    ORDER_BOOK_TABLE, TRADES_TABLE, OPTION_ORDER_BOOK_TABLE, OPTION_TRADES_TABLE,
    STOCK_ORDER_BOOK_TABLE, STOCK_TRADES_TABLE,
    ORDER_BOOK_COLUMNS, TRADES_COLUMNS, OPTION_ORDER_BOOK_COLUMNS,
    OPTION_TRADES_COLUMNS, STOCK_ORDER_BOOK_COLUMNS, STOCK_TRADES_COLUMNS,
)


_TABLES = {
    ORDER_BOOK_TABLE: (ORDER_BOOK_COLUMNS, _row_to_dict_ob, "depth_level"),
    TRADES_TABLE: (TRADES_COLUMNS, _row_to_dict_tr, "trade_id"),
    OPTION_ORDER_BOOK_TABLE: (OPTION_ORDER_BOOK_COLUMNS, _row_to_dict_opt_ob, "depth_level"),
    OPTION_TRADES_TABLE: (OPTION_TRADES_COLUMNS, _row_to_dict_opt_tr, "trade_id"),
    STOCK_ORDER_BOOK_TABLE: (STOCK_ORDER_BOOK_COLUMNS, _row_to_dict_stk_ob, "depth_level"),
    STOCK_TRADES_TABLE: (STOCK_TRADES_COLUMNS, _row_to_dict_stk_tr, "trade_id"),
}


async def latest_market_date(table: str) -> date | None:
    if table not in _TABLES:
        raise ValueError("Unsupported market table")
    client = await get_async_client()
    # Find the newest month from part metadata, then read only that partition.
    result = await client.query(
        "SELECT max(partition) FROM system.parts "
        "WHERE database = currentDatabase() AND table = {table:String} AND active AND rows > 0",
        parameters={"table": table},
    )
    month = result.result_rows[0][0] if result.result_rows else None
    if not month:
        return None
    result = await client.query(
        f"SELECT maxOrNull(trade_date) FROM `{table}` "
        "WHERE toYYYYMM(trade_date) = {month:UInt32}",
        parameters={"month": int(month)},
    )
    return result.result_rows[0][0] if result.result_rows else None


async def market_data_page(
    table: str,
    filters: dict[str, Any],
    cursor: tuple[int, str, int] | None = None,
    backwards: bool = False,
    limit: int = 101,
) -> list[dict[str, Any]]:
    columns, convert, row_id = _TABLES[table]
    if not isinstance(filters.get("trade_date"), date):
        raise ValueError("A valid trade date is required")
    if not 1 <= limit <= 101:
        raise ValueError("Page size must be between 1 and 101")
    specs = (_ob_filters if row_id == "depth_level" else _tr_filters)(**filters)
    where, params = _build_where(specs)
    if cursor is not None:
        # The negated time preserves newest-first ordering with ascending tie-breakers.
        where += (
            f" AND tuple(-toInt64(trade_time), instrument_code, {row_id}) "
            f"{'<' if backwards else '>'} "
            "tuple({cursor_time:Int64}, {cursor_code:String}, {cursor_id:UInt64})"
        )
        params.update(cursor_time=-cursor[0], cursor_code=cursor[1], cursor_id=cursor[2])
    order = (
        f"trade_time ASC, instrument_code DESC, {row_id} DESC" if backwards else
        f"trade_time DESC, instrument_code ASC, {row_id} ASC"
    )
    params["limit"] = limit
    client = await get_async_client()
    result = await client.query(
        f"SELECT {', '.join(columns)} FROM `{table}` FINAL {where} "
        f"ORDER BY {order} LIMIT {{limit:UInt32}}",
        parameters=params,
    )
    return [convert(row) for row in result.result_rows]
