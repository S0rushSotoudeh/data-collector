import asyncio
import sys
from datetime import date, timedelta

from src.collectors.bond.instrument_sync import sync_instruments_to_pg
from src.collectors.bond.order_book_fetcher import backfill_order_books

SLEEP_BETWEEN_DAYS = 5.0
DAYS_TO_FETCH = 7


async def main() -> None:
    print("Phase 1: Sync bond instruments to PostgreSQL...")
    result = await sync_instruments_to_pg()
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

    print(f"\nPhase 2: Backfill order books for {DAYS_TO_FETCH} days...")
    print(f"  Date range: {start_date} to {end_date}")

    current = start_date
    while current <= end_date:
        day_label = current.isoformat()
        print(f"\n  [{day_label}] Fetching...")
        try:
            result = await backfill_order_books(
                start_date=current,
                end_date=current,
            )
            rows = result["total_rows"]
            errs = result["errors"]
            total_rows += rows
            total_errors += len(errs)
            print(f"  [{day_label}] Inserted {rows} rows, Errors: {len(errs)}")
            if errs:
                for e in errs:
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