from typing import Any

from clickhouse_connect.driver import Client

from src.db.clickhouse import _ensure_client, price_to_storage
from src.db.clickhouse.schema import (
    ORDER_BOOK_TABLE,
    ORDER_BOOK_COLUMNS,
    TRADES_TABLE,
    TRADES_COLUMNS,
    YIELD_CURVE_FITS_TABLE,
    YIELD_CURVE_FITS_COLUMNS,
    YIELD_CURVE_BONDS_TABLE,
    YIELD_CURVE_BONDS_COLUMNS,
    OPTION_ORDER_BOOK_TABLE,
    OPTION_ORDER_BOOK_COLUMNS,
    OPTION_TRADES_TABLE,
    OPTION_TRADES_COLUMNS,
)


def insert_stock_order_book(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    for row in rows:
        if "bid_price" in row:
            row["bid_price"] = price_to_storage(row["bid_price"])
        if "ask_price" in row:
            row["ask_price"] = price_to_storage(row["ask_price"])
    data = [tuple(row.get(col) for col in ORDER_BOOK_COLUMNS) for row in rows]
    c.insert(ORDER_BOOK_TABLE, data, column_names=ORDER_BOOK_COLUMNS)


def insert_stock_trades(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    for row in rows:
        if "price" in row:
            row["price"] = price_to_storage(row["price"])
        if "value" in row:
            row["value"] = price_to_storage(row["value"])
    data = [tuple(row.get(col) for col in TRADES_COLUMNS) for row in rows]
    c.insert(TRADES_TABLE, data, column_names=TRADES_COLUMNS)


def insert_option_order_book(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    for row in rows:
        if "bid_price" in row:
            row["bid_price"] = price_to_storage(row["bid_price"])
        if "ask_price" in row:
            row["ask_price"] = price_to_storage(row["ask_price"])
    data = [tuple(row.get(col) for col in OPTION_ORDER_BOOK_COLUMNS) for row in rows]
    c.insert(OPTION_ORDER_BOOK_TABLE, data, column_names=OPTION_ORDER_BOOK_COLUMNS)


def insert_option_trades(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    for row in rows:
        if "price" in row:
            row["price"] = price_to_storage(row["price"])
        if "value" in row:
            row["value"] = price_to_storage(row["value"])
    data = [tuple(row.get(col) for col in OPTION_TRADES_COLUMNS) for row in rows]
    c.insert(OPTION_TRADES_TABLE, data, column_names=OPTION_TRADES_COLUMNS)


def insert_yield_curve_fits(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    data = [tuple(row.get(col) for col in YIELD_CURVE_FITS_COLUMNS) for row in rows]
    c.insert(YIELD_CURVE_FITS_TABLE, data, column_names=YIELD_CURVE_FITS_COLUMNS)


def insert_yield_curve_bonds(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    data = [tuple(row.get(col) for col in YIELD_CURVE_BONDS_COLUMNS) for row in rows]
    c.insert(YIELD_CURVE_BONDS_TABLE, data, column_names=YIELD_CURVE_BONDS_COLUMNS)