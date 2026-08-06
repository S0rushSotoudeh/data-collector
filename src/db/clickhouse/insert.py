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
    STOCK_ORDER_BOOK_TABLE,
    STOCK_ORDER_BOOK_COLUMNS,
    STOCK_TRADES_TABLE,
    STOCK_TRADES_COLUMNS,
)


def _insert_order_book(
    rows: list[dict[str, Any]],
    table: str,
    columns: list[str],
    client: Client | None = None,
) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    for row in rows:
        if "bid_price" in row:
            row["bid_price"] = price_to_storage(row["bid_price"])
        if "ask_price" in row:
            row["ask_price"] = price_to_storage(row["ask_price"])
    data = [tuple(row.get(col) for col in columns) for row in rows]
    c.insert(table, data, column_names=columns)


def insert_bond_order_book(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    _insert_order_book(rows, ORDER_BOOK_TABLE, ORDER_BOOK_COLUMNS, client)


def insert_stock_order_book(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    _insert_order_book(rows, STOCK_ORDER_BOOK_TABLE, STOCK_ORDER_BOOK_COLUMNS, client)


def _insert_trades(
    rows: list[dict[str, Any]],
    table: str,
    columns: list[str],
    client: Client | None = None,
) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    for row in rows:
        if "price" in row:
            row["price"] = price_to_storage(row["price"])
        if "value" in row:
            row["value"] = price_to_storage(row["value"])
    data = [tuple(row.get(col) for col in columns) for row in rows]
    c.insert(table, data, column_names=columns)


def insert_bond_trades(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    _insert_trades(rows, TRADES_TABLE, TRADES_COLUMNS, client)


def insert_stock_trades(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    _insert_trades(rows, STOCK_TRADES_TABLE, STOCK_TRADES_COLUMNS, client)


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
