from __future__ import annotations

from datetime import date
from typing import Any

from clickhouse_connect.driver import Client

from src.db.clickhouse import _ensure_client, get_async_client


IME_PHYSICAL_TRADES_TABLE = "ime_physical_trades"
IME_PHYSICAL_TRADES_COLUMNS = [
    "producer_code", "producer_name", "product_symbol", "product_name",
    "trade_date", "jalali_date", "delivery_date", "offer_id", "source_trade_pk",
    "contract_type", "price_thousand_rial", "quantity", "total_value_thousand_rial",
    "unit", "currency", "hall", "warehouse", "packet_name", "settlement_type",
    "category", "raw_json", "ingested_at",
]

IME_PHYSICAL_TRADES_DDL = f"""
CREATE TABLE IF NOT EXISTS `{IME_PHYSICAL_TRADES_TABLE}` (
  producer_code UInt32,
  producer_name LowCardinality(String),
  product_symbol String,
  product_name String,
  trade_date Date,
  jalali_date FixedString(10),
  delivery_date Nullable(Date),
  offer_id String,
  source_trade_pk UInt64,
  contract_type LowCardinality(String),
  price_thousand_rial Decimal64(4),
  quantity Decimal64(3),
  total_value_thousand_rial Decimal64(3),
  unit LowCardinality(String),
  currency LowCardinality(String),
  hall LowCardinality(String),
  warehouse String,
  packet_name LowCardinality(String),
  settlement_type LowCardinality(String),
  category LowCardinality(String),
  raw_json String,
  ingested_at DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY (producer_code, trade_date, product_symbol, offer_id, contract_type, source_trade_pk)
"""


def insert_ime_physical_trades(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    data = [tuple(row.get(column) for column in IME_PHYSICAL_TRADES_COLUMNS) for row in rows]
    c.insert(IME_PHYSICAL_TRADES_TABLE, data, column_names=IME_PHYSICAL_TRADES_COLUMNS)


def _filters(
    producer_code: int | None,
    product_symbol: str | None,
    trade_date: date | None,
    contract_type: str | None,
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if producer_code is not None:
        clauses.append("producer_code = {producer_code:UInt32}")
        params["producer_code"] = producer_code
    if product_symbol:
        clauses.append("product_symbol = {product_symbol:String}")
        params["product_symbol"] = product_symbol
    if trade_date:
        clauses.append("trade_date = {trade_date:Date}")
        params["trade_date"] = trade_date
    if contract_type:
        clauses.append("contract_type = {contract_type:String}")
        params["contract_type"] = contract_type
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _row(values: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(IME_PHYSICAL_TRADES_COLUMNS, values))


async def get_ime_trades_paginated(
    producer_code: int | None = None,
    product_symbol: str | None = None,
    trade_date: date | None = None,
    contract_type: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    where, params = _filters(producer_code, product_symbol, trade_date, contract_type)
    params.update({"limit": limit, "offset": offset})
    columns = ", ".join(f"`{column}`" for column in IME_PHYSICAL_TRADES_COLUMNS)
    result = await client.query(
        f"SELECT {columns} FROM `{IME_PHYSICAL_TRADES_TABLE}` FINAL {where} "
        "ORDER BY trade_date DESC, product_symbol, offer_id, contract_type "
        "LIMIT {limit:UInt32} OFFSET {offset:UInt32}",
        parameters=params,
    )
    return [_row(values) for values in result.result_rows]


async def count_ime_trades(
    producer_code: int | None = None,
    product_symbol: str | None = None,
    trade_date: date | None = None,
    contract_type: str | None = None,
) -> int:
    client = await get_async_client()
    where, params = _filters(producer_code, product_symbol, trade_date, contract_type)
    result = await client.query(
        f"SELECT count() FROM `{IME_PHYSICAL_TRADES_TABLE}` FINAL {where}", parameters=params
    )
    return int(result.result_rows[0][0]) if result.result_rows else 0


async def get_ime_price_volume_points(
    producer_code: int,
    product_symbol: str,
    from_date: date,
    to_date: date,
) -> list[dict[str, Any]]:
    client = await get_async_client()
    result = await client.query(
        f"SELECT trade_date, jalali_date, offer_id, source_trade_pk, contract_type, "
        f"price_thousand_rial, quantity, unit "
        f"FROM `{IME_PHYSICAL_TRADES_TABLE}` FINAL "
        "WHERE producer_code = {producer_code:UInt32} "
        "AND product_symbol = {product_symbol:String} "
        "AND trade_date BETWEEN {from_date:Date} AND {to_date:Date} "
        "ORDER BY trade_date, offer_id, contract_type",
        parameters={
            "producer_code": producer_code, "product_symbol": product_symbol,
            "from_date": from_date, "to_date": to_date,
        },
    )
    return [
        {
            "trade_date": values[0], "jalali_date": str(values[1]).strip(),
            "offer_id": values[2], "source_trade_pk": values[3], "contract_type": values[4],
            "price_thousand_rial": values[5], "quantity": values[6], "unit": values[7],
        }
        for values in result.result_rows
    ]
