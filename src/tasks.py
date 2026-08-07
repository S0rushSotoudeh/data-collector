import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable

from celery import shared_task

logger = logging.getLogger(__name__)


def _set_collection_run(run_id: str | None, status: str, result: dict | None = None, error: str | None = None) -> None:
    if not run_id:
        return
    from src.services.operation_runs import fail_run, finish_run, update_run

    if status == "failed":
        fail_run(run_id, error or "collection task failed")
    elif status == "completed":
        finish_run(run_id, result or {})
    else:
        update_run(run_id, status=status, error=error or "")


def _collection_run_id(task: Any, explicit_run_id: str | None = None) -> str | None:
    if explicit_run_id:
        return explicit_run_id
    headers = getattr(task.request, "headers", None) or {}
    value = headers.get("operation_run_id")
    return str(value) if value else None


def _run_collection(
    task: Any,
    collect: Callable[[Any], Awaitable[dict]],
    *,
    explicit_run_id: str | None = None,
) -> dict:
    from src.services.operation_runs import RunProgressReporter

    run_id = _collection_run_id(task, explicit_run_id)
    progress = RunProgressReporter(run_id)
    _set_collection_run(run_id, "running")
    try:
        result = asyncio.run(collect(progress))
        _set_collection_run(run_id, "completed", result)
        return result
    except Exception as exc:
        _set_collection_run(run_id, "failed", error=str(exc))
        raise

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
from src.collectors.stock.instrument_sync import sync_stock_instruments_to_pg
from src.collectors.stock.order_book_fetcher import backfill_stock_order_books
from src.collectors.stock.trade_fetcher import backfill_stock_trades


@shared_task(bind=True)
def sync_bond_instruments(self) -> dict:
    return _run_collection(self, lambda progress: sync_instruments_to_pg(progress=progress))


@shared_task(bind=True)
def fetch_yesterday_bond_order_book(self) -> dict:
    yesterday = date.today() - timedelta(days=1)
    return _run_collection(
        self,
        lambda progress: backfill_order_books(start_date=yesterday, end_date=yesterday, progress=progress),
    )


@shared_task(bind=True)
def backfill_bond_order_books_task(self, start_date_str: str, end_date_str: str, collection_run_id: str | None = None) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)

    async def collect(progress):
        codes = await get_instrument_codes_active_in_range(start, end)
        result = await backfill_order_books(start_date=start, end_date=end, instrument_codes=codes, progress=progress)
        result["instrument_count"] = len(codes)
        return result

    return _run_collection(self, collect, explicit_run_id=collection_run_id)


@shared_task(bind=True)
def fetch_yesterday_bond_trades(self) -> dict:
    yesterday = date.today() - timedelta(days=1)

    async def collect(progress):
        codes = await get_instrument_codes_active_in_range(yesterday, yesterday)
        return await backfill_trades(
            start_date=yesterday, end_date=yesterday, instrument_codes=codes, progress=progress,
        )

    return _run_collection(self, collect)


@shared_task(bind=True)
def backfill_bond_trades_task(self, start_date_str: str, end_date_str: str, collection_run_id: str | None = None) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)

    async def collect(progress):
        codes = await get_instrument_codes_active_in_range(start, end)
        result = await backfill_trades(start_date=start, end_date=end, instrument_codes=codes, progress=progress)
        result["instrument_count"] = len(codes)
        return result

    return _run_collection(self, collect, explicit_run_id=collection_run_id)


@shared_task(bind=True)
def sync_option_instruments(self) -> dict:
    return _run_collection(self, lambda progress: sync_option_instruments_to_pg(progress=progress))


@shared_task(bind=True)
def sync_stock_instruments(self) -> dict:
    return _run_collection(self, lambda progress: sync_stock_instruments_to_pg(progress=progress))


@shared_task(bind=True)
def backfill_stock_order_books_task(self, start_date_str: str, end_date_str: str, collection_run_id: str | None = None) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    return _run_collection(
        self,
        lambda progress: backfill_stock_order_books(start_date=start, end_date=end, progress=progress),
        explicit_run_id=collection_run_id,
    )


@shared_task(bind=True)
def backfill_stock_trades_task(self, start_date_str: str, end_date_str: str, collection_run_id: str | None = None) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    return _run_collection(
        self,
        lambda progress: backfill_stock_trades(start_date=start, end_date=end, progress=progress),
        explicit_run_id=collection_run_id,
    )


@shared_task(bind=True)
def fetch_yesterday_stock_orderbook(self) -> dict:
    yesterday = date.today() - timedelta(days=1)
    return _run_collection(
        self,
        lambda progress: backfill_stock_order_books(start_date=yesterday, end_date=yesterday, progress=progress),
    )


@shared_task(bind=True)
def fetch_yesterday_stock_trades(self) -> dict:
    yesterday = date.today() - timedelta(days=1)
    return _run_collection(
        self,
        lambda progress: backfill_stock_trades(start_date=yesterday, end_date=yesterday, progress=progress),
    )


@shared_task(bind=True)
def fetch_yesterday_option_orderbook(self) -> dict:
    yesterday = date.today() - timedelta(days=1)
    return _run_collection(
        self,
        lambda progress: backfill_option_order_books(start_date=yesterday, end_date=yesterday, progress=progress),
    )


@shared_task(bind=True)
def backfill_option_order_books_task(self, start_date_str: str, end_date_str: str, collection_run_id: str | None = None) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)

    async def collect(progress):
        codes = await get_option_codes_active_in_range(start, end)
        result = await backfill_option_order_books(start_date=start, end_date=end, instrument_codes=codes, progress=progress)
        result["instrument_count"] = len(codes)
        return result

    return _run_collection(self, collect, explicit_run_id=collection_run_id)


@shared_task(bind=True)
def fetch_yesterday_option_trades(self) -> dict:
    yesterday = date.today() - timedelta(days=1)

    async def collect(progress):
        codes = await get_option_codes_active_in_range(yesterday, yesterday)
        return await backfill_option_trades(
            start_date=yesterday, end_date=yesterday, instrument_codes=codes, progress=progress,
        )

    return _run_collection(self, collect)


@shared_task(bind=True)
def backfill_option_trades_task(self, start_date_str: str, end_date_str: str, collection_run_id: str | None = None) -> dict:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)

    async def collect(progress):
        codes = await get_option_codes_active_in_range(start, end)
        result = await backfill_option_trades(start_date=start, end_date=end, instrument_codes=codes, progress=progress)
        result["instrument_count"] = len(codes)
        return result

    return _run_collection(self, collect, explicit_run_id=collection_run_id)


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


@shared_task
def run_parity_analysis(run_id: str) -> dict:
    """Process an immutable parity run one trading date at a time."""
    from src.analytics.parity_engine import fail_run, process_run

    try:
        return process_run(run_id)
    except Exception as exc:
        logger.exception("Parity analysis run %s failed", run_id)
        try:
            fail_run(run_id, str(exc))
        except Exception:
            logger.exception("Could not mark parity run %s failed", run_id)
        raise


@shared_task
def run_box_spread_analysis(run_id: str) -> dict:
    """Replay one selected box-spread pair without placing orders."""
    from src.analytics.box_spread_engine import fail_run, process_run

    try:
        return process_run(run_id)
    except Exception as exc:
        logger.exception("Box-spread analysis run %s failed", run_id)
        try:
            fail_run(run_id, str(exc))
        except Exception:
            logger.exception("Could not mark box-spread run %s failed", run_id)
        raise


@shared_task
def run_iv_surface(run_id: str) -> dict:
    """Process a manually submitted immutable historical IV replay."""
    from src.analytics.iv_engine import fail_run, process_run

    try:
        return process_run(run_id)
    except Exception as exc:
        logger.exception("IV surface run %s failed", run_id)
        try:
            fail_run(run_id, str(exc))
        except Exception:
            logger.exception("Could not mark IV surface run %s failed", run_id)
        raise


@shared_task(bind=True, max_retries=2)
def run_option_mispricing(self, run_id: str) -> dict:
    """Run an immutable market-wide option mispricing replay."""
    from src.analytics.mispricing_engine import fail_run, process_run

    try:
        return process_run(run_id)
    except Exception as exc:
        if self.request.retries < self.max_retries:
            logger.warning("Retrying option mispricing run %s after error: %s", run_id, exc)
            raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
        logger.exception("Option mispricing run %s failed", run_id)
        try:
            fail_run(run_id, str(exc))
        except Exception:
            logger.exception("Could not mark option mispricing run %s failed", run_id)
        raise


@shared_task
def compute_option_market_potential_daily(day_str: str | None = None) -> dict:
    from src.analytics.market_potential import compute_daily

    target = date.fromisoformat(day_str) if day_str else date.today() - timedelta(days=1)
    return compute_daily(target)
