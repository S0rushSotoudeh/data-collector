import asyncio
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.collectors.bond.tsetmc_client import TsetmcClient
from src.collectors.bond.transformer import best_limits_to_order_book_rows
from src.db.clickhouse.bond import insert_order_book
from src.db.models.bond import BondInstrument
from src.db.session import SessionLocal


async def get_active_instrument_codes() -> list[str]:
    session: Session
    with SessionLocal() as session:
        stmt = select(BondInstrument.instrument_code).where(
            BondInstrument.status == "active"
        )
        rows = session.execute(stmt).all()
        return [row[0] for row in rows]


async def get_instrument_codes_active_in_range(
    start_date: date, end_date: date
) -> list[str]:
    session: Session
    with SessionLocal() as session:
        stmt = (
            select(BondInstrument.instrument_code)
            .where(BondInstrument.last_trade_date >= start_date)
            .where(BondInstrument.last_trade_date.isnot(None))
        )
        rows = session.execute(stmt).all()
        return [row[0] for row in rows]


async def fetch_order_book_for_date(
    client: TsetmcClient,
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
    insert_order_book(rows)
    return len(rows)


async def backfill_order_books(
    start_date: date,
    end_date: date,
    instrument_codes: list[str] | None = None,
    concurrency: int = 5,
) -> dict[str, Any]:
    errors: list[str] = []
    total_rows = 0
    total_days_tried = 0

    async with TsetmcClient(concurrency=concurrency) as client:
        codes = instrument_codes or await get_active_instrument_codes()

        current = start_date
        while current <= end_date:
            for code in codes:
                try:
                    rows = await fetch_order_book_for_date(client, code, current)
                    total_rows += rows
                    total_days_tried += 1
                except Exception as e:
                    errors.append(f"{code}@{current.isoformat()}: {e}")
            current += timedelta(days=1)

    return {
        "total_days_tried": total_days_tried,
        "total_rows": total_rows,
        "errors": errors,
    }