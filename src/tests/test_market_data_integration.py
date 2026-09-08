"""Run with MARKET_DATA_INTEGRATION=1 in Compose; uses an isolated temporary DB."""

import os
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import clickhouse_connect
import pytest

from src.db.clickhouse import market_data as db
from src.db.clickhouse import schema


pytestmark = pytest.mark.skipif(
    os.environ.get("MARKET_DATA_INTEGRATION") != "1", reason="Opt-in local ClickHouse integration",
)


@pytest.fixture
async def market_client():
    # Always target the local Compose service, irrespective of application host settings.
    credentials = dict(host="clickhouse", port=8123, username=os.environ["CLICKHOUSE_USER"],
                       password=os.environ["CLICKHOUSE_PASSWORD"])
    control = await clickhouse_connect.get_async_client(**credentials)
    database = "test_market_admin_" + uuid4().hex
    await control.command(f"CREATE DATABASE {database}")
    client = None
    try:
        client = await clickhouse_connect.get_async_client(**credentials, database=database)
        with patch.object(db, "get_async_client", AsyncMock(return_value=client)):
            yield client
    finally:
        if client is not None:
            await client.close()
        await control.command(f"DROP DATABASE {database} SYNC")
        await control.close()


@pytest.mark.parametrize("table,ddl", [
    ("bond_trades", schema._TRADES_DDL), ("bond_order_book", schema._ORDER_BOOK_DDL),
    ("stock_trades", schema._STOCK_TRADES_DDL), ("stock_order_book", schema._STOCK_ORDER_BOOK_DDL),
    ("option_trades", schema._OPTION_TRADES_DDL), ("option_order_book", schema._OPTION_ORDER_BOOK_DDL),
])
async def test_cursor_walk_preserves_ties_and_replacements(market_client, table, ddl):
    client = market_client
    await client.command(ddl)
    assert await db.latest_market_date(table) is None
    await client.command(f"SYSTEM STOP MERGES {table}")
    columns, _, row_id = db._TABLES[table]
    day = date(2026, 8, 11)
    now = datetime.now().replace(microsecond=0)
    data = []
    for i in range(207):
        row = dict.fromkeys(columns, 1)
        row.update(instrument_code=str(i // 5), trade_date=day, trade_time=34200 + i // 50,
                   trade_id=i, depth_level=i % 5 + 1, data_source="tsetmc", ingested_at=now,
                   price=100, value=100, bid_price=100, ask_price=101, is_canceled=0)
        data.append([row[c] for c in columns])
    await client.insert(table, data, column_names=columns)
    old = data[0].copy()
    old[columns.index("trade_date")] = date(2026, 7, 1)
    await client.insert(table, [old], column_names=columns)
    corrected = data[0].copy()
    price_field = "bid_price" if row_id == "depth_level" else "price"
    corrected[columns.index(price_field)] = 222
    corrected[columns.index("ingested_at")] = now + timedelta(seconds=1)
    await client.insert(table, [corrected], column_names=columns)
    assert await db.latest_market_date(table) == day

    def cursor(row):
        return row["trade_time"], row["instrument_code"], row[row_id]

    filters = {"trade_date": day}
    first = (await db.market_data_page(table, filters))[:100]
    second = (await db.market_data_page(table, filters, cursor(first[-1])))[:100]
    third = await db.market_data_page(table, filters, cursor(second[-1]))
    combined = first + second + third
    assert len(third) == 7
    expected = sorted(
        [(r[columns.index("trade_time")], r[0], r[columns.index(row_id)]) for r in data],
        key=lambda key: (-key[0], key[1], key[2]),
    )
    assert list(map(cursor, combined)) == expected
    assert len(set(map(cursor, combined))) == 207
    backwards = (await db.market_data_page(table, filters, cursor(second[0]), backwards=True))[:100]
    assert list(map(cursor, reversed(backwards))) == list(map(cursor, first))
    replacement = [r for r in combined if r["instrument_code"] == "0" and r[row_id] == data[0][columns.index(row_id)]]
    assert replacement[0][price_field] == 222
    if row_id == "trade_id":
        filtered = await db.market_data_page(table, {"trade_date": day, "instrument_code": "0", "max_price": 100})
        assert all(row["trade_id"] != 0 for row in filtered)


async def test_one_million_historical_rows_are_pruned(market_client):
    client = market_client
    await client.command(schema._STOCK_TRADES_DDL)
    await client.command(
        "INSERT INTO stock_trades (instrument_code, trade_date, trade_time, trade_id, price, volume, value, data_source) "
        "SELECT 'old', toDate('2026-07-01'), number % 86400, number, 100, 1, 100, 'test' FROM numbers(1000000)"
    )
    await client.command(
        "INSERT INTO stock_trades (instrument_code, trade_date, trade_time, trade_id, price, volume, value, data_source) "
        "SELECT 'new', toDate('2026-08-11'), number, number, 100, 1, 100, 'test' FROM numbers(207)"
    )
    old_count = await client.query("SELECT count() FROM stock_trades FINAL")
    queries = []
    original_query = client.query

    async def record_query(*args, **kwargs):
        result = await original_query(*args, **kwargs)
        queries.append(result.summary)
        return result

    with patch.object(client, "query", record_query):
        latest = await db.latest_market_date("stock_trades")
        result = await db.market_data_page("stock_trades", {"trade_date": latest})
    assert len(result) == 101
    assert old_count.result_rows[0][0] == 1000207
    old_reads = int(old_count.summary["read_rows"])
    new_reads = sum(int(q["read_rows"]) for q in queries)
    assert new_reads < old_reads / 100
    print(f"Historical count read {old_reads:,} rows; new initial page including date lookup read {new_reads:,} rows.")
