from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from clickhouse_connect.driver import Client

from src.db.clickhouse import _ensure_client, get_async_client

TABLE = "deposit_certificate_order_book_stream"
SYMBOLS = ("GOLDBAR", "GOLDCOIN")
COLUMNS = [
    "event_id", "book_hash", "contract_id", "symbol", "provider_event_at", "received_at", "redis_id",
    "bid_price_1", "bid_volume_1", "bid_price_2", "bid_volume_2", "bid_price_3", "bid_volume_3",
    "ask_price_1", "ask_volume_1", "ask_price_2", "ask_volume_2", "ask_price_3", "ask_volume_3",
]
TEHRAN = ZoneInfo("Asia/Tehran")


def insert_order_books(rows: list[dict[str, Any]], client: Client | None = None) -> None:
    if not rows:
        return
    c = _ensure_client(client)
    c.insert(TABLE, [tuple(row[name] for name in COLUMNS) for row in rows], column_names=COLUMNS)


def _rows(result) -> list[dict[str, Any]]:
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def _where(symbol: str | None, start: datetime | None, end: datetime | None) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if symbol:
        clauses.append("symbol = {symbol:String}")
        params["symbol"] = symbol
    if start:
        clauses.append("provider_event_at >= {start:DateTime64(3)}")
        params["start"] = start
    if end:
        clauses.append("provider_event_at <= {end:DateTime64(3)}")
        params["end"] = end
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


async def latest(symbol: str | None = None) -> list[dict[str, Any]]:
    client = await get_async_client()
    where, params = _where(symbol, None, None)
    result = await client.query(
        f"SELECT {', '.join(COLUMNS)} FROM `{TABLE}` FINAL{where} "
        "ORDER BY provider_event_at DESC LIMIT 1 BY symbol",
        parameters=params,
    )
    return sorted(_rows(result), key=lambda row: row["symbol"])


async def history(symbol: str, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
    client = await get_async_client()
    where, params = _where(symbol, start, end)
    params["limit"] = limit
    result = await client.query(
        f"SELECT {', '.join(COLUMNS)} FROM `{TABLE}` FINAL{where} "
        "ORDER BY provider_event_at DESC LIMIT {limit:UInt32}",
        parameters=params,
    )
    return _rows(result)


async def intraday_best_quotes(
    symbol: str, trade_date: date, from_time: int = 120000, to_time: int = 180000
) -> list[dict[str, Any]]:
    client = await get_async_client()
    as_time = lambda value: time(value // 10000, value // 100 % 100, value % 100)
    start = datetime.combine(trade_date, as_time(from_time), TEHRAN)
    end = datetime.combine(trade_date, as_time(to_time), TEHRAN)
    result = await client.query(
        f"SELECT "
        "toUInt32(formatDateTime(toStartOfInterval(provider_event_at, INTERVAL 5 SECOND), '%H%i%s')) AS trade_time, "
        "argMax(bid_price_1, tuple(provider_event_at, received_at, event_id)) AS best_bid, "
        "argMax(ask_price_1, tuple(provider_event_at, received_at, event_id)) AS best_ask "
        f"FROM `{TABLE}` FINAL "
        "WHERE symbol = {symbol:String} "
        "AND provider_event_at >= {start:DateTime64(3)} "
        "AND provider_event_at <= {end:DateTime64(3)} "
        "GROUP BY trade_time ORDER BY trade_time",
        parameters={"symbol": symbol, "start": start, "end": end},
    )
    return [
        {"trade_time": int(row[0]), "best_bid": float(row[1]), "best_ask": float(row[2])}
        for row in result.result_rows
    ]


async def paginated(
    symbol: str | None, trade_date: date | None, offset: int, limit: int
) -> tuple[int, list[dict[str, Any]]]:
    start = datetime.combine(trade_date, time.min, TEHRAN) if trade_date else None
    end = start + timedelta(days=1) if start else None
    where, params = _where(symbol, start, end)
    if end:
        where = where.replace("provider_event_at <=", "provider_event_at <")
    client = await get_async_client()
    count = await client.query(f"SELECT count() FROM `{TABLE}` FINAL{where}", parameters=params)
    params.update(limit=limit, offset=offset)
    result = await client.query(
        f"SELECT {', '.join(COLUMNS)} FROM `{TABLE}` FINAL{where} "
        "ORDER BY provider_event_at DESC LIMIT {limit:UInt32} OFFSET {offset:UInt32}",
        parameters=params,
    )
    total = int(count.result_rows[0][0]) if count.result_rows else 0
    return total, _rows(result)
