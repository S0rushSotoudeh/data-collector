from typing import Any

from clickhouse_connect.driver import Client

from src.db.clickhouse import _ensure_client, price_to_storage
from src.db.clickhouse.schema import ORDER_BOOK_TABLE, ORDER_BOOK_COLUMNS, TRADES_TABLE, TRADES_COLUMNS


def insert_order_book(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    for row in rows:
        if "bid_price" in row:
            row["bid_price"] = price_to_storage(row["bid_price"])
        if "ask_price" in row:
            row["ask_price"] = price_to_storage(row["ask_price"])
    c.insert(ORDER_BOOK_TABLE, rows, column_names=ORDER_BOOK_COLUMNS)


def insert_trades(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    for row in rows:
        if "price" in row:
            row["price"] = price_to_storage(row["price"])
        if "value" in row:
            row["value"] = price_to_storage(row["value"])
    c.insert(TRADES_TABLE, rows, column_names=TRADES_COLUMNS)