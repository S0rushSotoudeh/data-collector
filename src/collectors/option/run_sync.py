import asyncio
import sys
from datetime import date, timedelta

from src.collectors.option.instrument_sync import sync_option_instruments_to_pg
from src.collectors.option.order_book_fetcher import backfill_option_order_books
from src.collectors.option.trade_fetcher import backfill_option_trades

SLEEP_BETWEEN_DAYS = 5.0
DAYS_TO_FETCH = 7


async def main() -> None:
    print("Phase 1: Sync option instruments to PostgreSQL...")
    result = await sync_option_instruments_to_pg()
    synced = result["synced"]
    errors = result["errors"]
    print(f"  Synced: {synced}, Errors: {len(errors)}")
    if errors:
        for e in errors:
            print(f"    {e}")

    today = date.today()
    end_date = today - timedelta(days=1)
    start_date = end_date - timedelta(days=DAYS_TO_FETCH - 1)

    total_rows = 0
    total_errors = 0

    print(f"\nPhase 2: Backfill order books + trades for {DAYS_TO_FETCH} days...")
    print(f"  Date range: {start_date} to {end_date}")

    current = start_date
    while current <= end_date:
        day_label = current.isoformat()
        print(f"\n  [{day_label}] Fetching...")
        try:
            ob_result = await backfill_option_order_books(
                start_date=current,
                end_date=current,
            )
            ob_rows = ob_result["total_rows"]
            ob_errs = ob_result["errors"]
            total_rows += ob_rows
            total_errors += len(ob_errs)
            print(f"  [{day_label}] Order books inserted {ob_rows} rows, Errors: {len(ob_errs)}")
            if ob_errs:
                for e in ob_errs:
                    print(f"    {e}")

            tr_result = await backfill_option_trades(
                start_date=current,
                end_date=current,
            )
            tr_rows = tr_result["total_rows"]
            tr_errs = tr_result["errors"]
            total_rows += tr_rows
            total_errors += len(tr_errs)
            print(f"  [{day_label}] Trades inserted {tr_rows} rows, Errors: {len(tr_errs)}")
            if tr_errs:
                for e in tr_errs:
                    print(f"    {e}")
        except Exception as e:
            total_errors += 1
            print(f"  [{day_label}] FAILED: {e}")

        if current < end_date:
            print(f"  Sleeping {SLEEP_BETWEEN_DAYS}s...")
            await asyncio.sleep(SLEEP_BETWEEN_DAYS)

        current += timedelta(days=1)

    print(f"\nDone. Total rows inserted: {total_rows}, Total errors: {total_errors}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)
