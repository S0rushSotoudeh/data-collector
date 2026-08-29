import asyncio
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.collectors.stock.market_watch_client import StockTsetmcClient
from src.collectors.gold.transformer import best_limits_to_order_book_rows
from src.db.clickhouse.gold import insert_gold_order_book
from src.db.models.gold import GoldInstrument
from src.db.session import SessionLocal
from src.services.operation_runs import RunProgressReporter


async def get_active_gold_codes() -> list[str]:
    session: Session
    with SessionLocal() as session:
        stmt = select(GoldInstrument.instrument_code).where(
            GoldInstrument.status == "active"
        )
        rows = session.execute(stmt).all()
        return [row[0] for row in rows]


async def get_gold_codes_active_in_range(
    start_date: date, end_date: date
) -> list[str]:
    session: Session
    with SessionLocal() as session:
        stmt = (
            select(GoldInstrument.instrument_code)
            .where(GoldInstrument.last_trade_date >= start_date)
            .where(GoldInstrument.last_trade_date.isnot(None))
        )
        rows = session.execute(stmt).all()
        return [row[0] for row in rows]


async def fetch_gold_order_book_for_date(
    client: StockTsetmcClient,
    instrument_code: str,
    trade_date: date,
) -> int:
    limits = await client.get_best_limits(instrument_code, trade_date)
    if not limits:
        return 0
    rows = best_limits_to_order_book_rows(
        limits=limits,
        instrument_code=instrument_code,
        trade_date=trade_date,
        data_source="tsetmc",
    )
    await asyncio.to_thread(insert_gold_order_book, rows)
    return len(rows)


async def backfill_gold_order_books(
    start_date: date,
    end_date: date,
    instrument_codes: list[str] | None = None,
    concurrency: int = 5,
    progress: RunProgressReporter | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    total_rows = 0
    total_days_tried = 0

    async with StockTsetmcClient(concurrency=concurrency) as client:
        codes = instrument_codes or await get_active_gold_codes()
        if progress:
            progress.set_total(len(codes) * ((end_date - start_date).days + 1))

        current = start_date
        while current <= end_date:
            for code in codes:
                rows = 0
                warning_count = 0
                try:
                    rows = await fetch_gold_order_book_for_date(client, code, current)
                    total_rows += rows
                    total_days_tried += 1
                except Exception as e:
                    errors.append(f"{code}@{current.isoformat()}: {e}")
                    warning_count = 1
                finally:
                    if progress:
                        progress.advance(output_count=rows, warning_count=warning_count)
            current += timedelta(days=1)

    return {
        "total_days_tried": total_days_tried,
        "total_rows": total_rows,
        "errors": errors,
    }
