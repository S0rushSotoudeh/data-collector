import asyncio
from datetime import date, timedelta
from typing import Any

from src.collectors.stock.market_watch_client import StockTsetmcClient
from src.collectors.stock.order_book_fetcher import get_active_stock_codes
from src.collectors.stock.transformer import trades_to_trade_rows
from src.db.clickhouse.stock import insert_stock_trades
from src.db.clickhouse.schema import STOCK_TRADES_TABLE


def _has_existing_stock_trades(instrument_code: str, trade_date: date) -> bool:
    from src.db.clickhouse import _ensure_client
    client = _ensure_client(None)
    q = f"SELECT count() FROM `{STOCK_TRADES_TABLE}` FINAL WHERE instrument_code = {{code:String}} AND trade_date = {{dt:Date}}"
    result = client.query(q, parameters={"code": instrument_code, "dt": trade_date})
    return result.result_rows[0][0] > 0


async def fetch_stock_trades_for_date(
    client: StockTsetmcClient,
    instrument_code: str,
    trade_date: date,
) -> int:
    trades = await client.get_trade_history(instrument_code, trade_date)
    if not trades:
        return 0
    rows = trades_to_trade_rows(trades, instrument_code, trade_date, "tsetmc")
    await asyncio.to_thread(insert_stock_trades, rows)
    return len(rows)


async def backfill_stock_trades(
    start_date: date,
    end_date: date,
    instrument_codes: list[str] | None = None,
    concurrency: int = 5,
) -> dict[str, Any]:
    errors: list[str] = []
    total_rows = 0
    total_days_tried = 0
    skipped = 0

    async with StockTsetmcClient(concurrency=concurrency) as client:
        codes = instrument_codes or await get_active_stock_codes()

        current = start_date
        while current <= end_date:
            for code in codes:
                if await asyncio.to_thread(_has_existing_stock_trades, code, current):
                    skipped += 1
                    continue
                try:
                    rows = await fetch_stock_trades_for_date(client, code, current)
                    total_rows += rows
                    total_days_tried += 1
                except Exception as e:
                    errors.append(f"{code}@{current.isoformat()}: {e}")
            current += timedelta(days=1)

    return {
        "total_days_tried": total_days_tried,
        "total_rows": total_rows,
        "skipped": skipped,
        "errors": errors,
    }
