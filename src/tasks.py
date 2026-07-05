import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from celery import shared_task

logger = logging.getLogger(__name__)

from src.collectors.bond.instrument_sync import sync_instruments_to_pg
from src.collectors.bond.order_book_fetcher import (
    backfill_order_books,
    get_instrument_codes_active_in_range,
)
from src.collectors.bond.trade_fetcher import backfill_trades
from src.collectors.option.instrument_sync import sync_option_instruments_to_pg
from src.collectors.option.order_book_fetcher import (
    backfill_option_order_books,
    get_option_codes_active_in_range,
)
from src.collectors.option.trade_fetcher import backfill_option_trades


@shared_task
def sync_bond_instruments() -> dict:
    return asyncio.run(sync_instruments_to_pg())


@shared_task
def fetch_yesterday_orderbook() -> dict:
    yesterday = date.today() - timedelta(days=1)
    return asyncio.run(
        backfill_order_books(start_date=yesterday, end_date=yesterday)
    )


@shared_task
def backfill_order_books_task(start_date_str: str, end_date_str: str) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    codes = asyncio.run(get_instrument_codes_active_in_range(start, end))
    result = asyncio.run(
        backfill_order_books(start_date=start, end_date=end, instrument_codes=codes)
    )
    result["instrument_count"] = len(codes)
    return result


@shared_task
def fetch_yesterday_trades() -> dict:
    yesterday = date.today() - timedelta(days=1)
    codes = asyncio.run(get_instrument_codes_active_in_range(yesterday, yesterday))
    return asyncio.run(
        backfill_trades(start_date=yesterday, end_date=yesterday, instrument_codes=codes)
    )


@shared_task
def backfill_trades_task(start_date_str: str, end_date_str: str) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    codes = asyncio.run(get_instrument_codes_active_in_range(start, end))
    result = asyncio.run(
        backfill_trades(start_date=start, end_date=end, instrument_codes=codes)
    )
    result["instrument_count"] = len(codes)
    return result


@shared_task
def sync_option_instruments() -> dict:
    return asyncio.run(sync_option_instruments_to_pg())


@shared_task
def fetch_yesterday_option_orderbook() -> dict:
    yesterday = date.today() - timedelta(days=1)
    return asyncio.run(
        backfill_option_order_books(start_date=yesterday, end_date=yesterday)
    )


@shared_task
def backfill_option_order_books_task(start_date_str: str, end_date_str: str) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    codes = asyncio.run(get_option_codes_active_in_range(start, end))
    result = asyncio.run(
        backfill_option_order_books(start_date=start, end_date=end, instrument_codes=codes)
    )
    result["instrument_count"] = len(codes)
    return result


@shared_task
def fetch_yesterday_option_trades() -> dict:
    yesterday = date.today() - timedelta(days=1)
    codes = asyncio.run(get_option_codes_active_in_range(yesterday, yesterday))
    return asyncio.run(
        backfill_option_trades(start_date=yesterday, end_date=yesterday, instrument_codes=codes)
    )


@shared_task
def backfill_option_trades_task(start_date_str: str, end_date_str: str) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    codes = asyncio.run(get_option_codes_active_in_range(start, end))
    result = asyncio.run(
        backfill_option_trades(start_date=start, end_date=end, instrument_codes=codes)
    )
    result["instrument_count"] = len(codes)
    return result


@shared_task
def compute_yield_curve_snapshot() -> dict:
    from src.analytics.engine import compute_curve_for_date
    from zoneinfo import ZoneInfo

    tehran = ZoneInfo("Asia/Tehran")
    now_tehran = datetime.now(tehran)
    hour = now_tehran.hour
    minute = now_tehran.minute
    market_open = (hour == 8 and minute >= 30) or (hour > 8 and hour < 15)
    if not market_open:
        return {"status": "skipped", "reason": "Outside market hours"}
    today_str = now_tehran.date().isoformat()
    return asyncio.run(compute_curve_for_date(today_str))


@shared_task(bind=True)
def backfill_yield_curves(self, start_date_str: str, end_date_str: str) -> dict:
    from src.analytics.engine import compute_curve_for_date
    from src.db.clickhouse import get_async_client

    async def _backfill():
        ch = await get_async_client()
        sd = date.fromisoformat(start_date_str)
        ed = date.fromisoformat(end_date_str)

        source_rows = (
            await ch.query(
                "SELECT DISTINCT trade_date FROM bond_order_book "
                "WHERE trade_date >= {sd:Date} AND trade_date <= {ed:Date} "
                "ORDER BY trade_date",
                parameters={"sd": sd, "ed": ed},
            )
        ).result_rows
        source_dates = {r[0] for r in source_rows}

        existing_rows = (
            await ch.query(
                "SELECT trade_date, curve_side FROM ("
                "  SELECT trade_date, curve_side, converged "
                "  FROM yield_curve_fits "
                "  WHERE trade_date >= {sd:Date} AND trade_date <= {ed:Date} "
                "  ORDER BY computed_at DESC "
                "  LIMIT 1 BY trade_date, curve_side"
                ") WHERE converged = 1",
                parameters={"sd": sd, "ed": ed},
            )
        ).result_rows
        done_sides = {(r[0], r[1]) for r in existing_rows}

        pending = []
        for d in sorted(source_dates):
            bid_done = (d, "bid") in done_sides
            ask_done = (d, "ask") in done_sides
            if bid_done and ask_done:
                continue
            pending.append(d)

        skipped = len(source_dates) - len(pending)
        total = len(pending)

        if skipped:
            logger.info(
                "Yield curve backfill: %d dates fully done, %d pending",
                skipped, total,
            )

        for i, d in enumerate(pending, 1):
            d_str = d.isoformat()
            logger.info("Yield curve backfill [%d/%d] %s", i, total, d_str)
            result = await compute_curve_for_date(d_str)
            logger.info("Yield curve backfill %s done: %s", d_str, result)

        return {
            "dates_processed": total,
            "dates_skipped": skipped,
        }

    return asyncio.run(_backfill())