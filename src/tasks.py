import asyncio
from datetime import date, timedelta

from celery import shared_task

from src.collectors.bond.instrument_sync import sync_instruments_to_pg
from src.collectors.bond.order_book_fetcher import backfill_order_books


@shared_task(serializer="pickle")
def sync_bond_instruments() -> dict:
    return asyncio.run(sync_instruments_to_pg())


@shared_task(serializer="pickle")
def fetch_yesterday_orderbook() -> dict:
    yesterday = date.today() - timedelta(days=1)
    return asyncio.run(
        backfill_order_books(start_date=yesterday, end_date=yesterday)
    )


@shared_task(serializer="pickle")
def backfill_order_books_range(start_date_str: str, end_date_str: str) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    return asyncio.run(
        backfill_order_books(start_date=start, end_date=end)
    )