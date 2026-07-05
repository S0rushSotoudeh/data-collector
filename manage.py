"""
Django-like management commands for data-collector.

Usage:
python manage.py shell                    # Open interactive Python shell
    python manage.py bond-sync                # Sync bonds + backfill last 7 days of order books
    python manage.py sync-instruments         # Celery Task 1: sync bond instruments to PostgreSQL
    python manage.py backfill-order-books     # Celery Task 3: backfill order books for a date range
    python manage.py backfill-trades          # Celery Task 4: backfill trades for a date range
    python manage.py option-sync              # Sync options + backfill last 7 days of order books + trades
    python manage.py sync-option-instruments  # Sync option instruments from TSETMC to PostgreSQL
    python manage.py backfill-option-order-books  # Backfill option order books for a date range
    python manage.py backfill-option-trades       # Backfill option trades for a date range
    python manage.py clickhouse migrate       # Apply all pending ClickHouse migrations
    python manage.py clickhouse downgrade      # Revert last ClickHouse migration
    python manage.py clickhouse history        # Show ClickHouse migration history
    python manage.py clickhouse pending        # List pending ClickHouse migrations
    python manage.py clickhouse check          # Exit non-zero if pending migrations exist
"""

import asyncio
import os
import sys
import argparse
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _get_db_url() -> str:
    user = os.getenv("POSTGRES_USER", "dc_user")
    password = os.getenv("POSTGRES_PASSWORD", "dc_pass")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "dc_metadata")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def _setup_imports():
    import src.db.models
    from src.db.models import BondInstrument, OptionInstrument
    from sqlmodel import SQLModel, Session, select

    engine = create_engine(_get_db_url())
    session = Session(engine)

    return {
        "engine": engine,
        "session": session,
        "Session": Session,
        "SQLModel": SQLModel,
        "select": select,
        "BondInstrument": BondInstrument,
        "OptionInstrument": OptionInstrument,
    }


def cmd_shell(args):
    namespace = _setup_imports()

    try:
        import IPython
        IPython.start_ipython(argv=[], user_ns=namespace)
    except ImportError:
        import code
        banner = "Data Collector shell — available: engine, session, BondInstrument, SQLModel, select"
        code.interact(banner=banner, local=namespace)


def cmd_ch_migrate(args):
    from src.db.clickhouse.schema import run_migrations

    applied = run_migrations()
    if applied:
        print(f"Applied {len(applied)} migration(s): {applied}")
    else:
        print("Already up to date — no migrations to apply.")


def cmd_ch_downgrade(args):
    from src.db.clickhouse.schema import downgrade_migration

    reverted = downgrade_migration()
    print(f"Reverted migration: {reverted}")


def cmd_ch_history(args):
    from src.db.clickhouse.schema import migration_history

    rows = migration_history()
    if not rows:
        print("No migrations have been applied.")
        return
    print(f"{'Version':>8}  {'Name':<40}  {'Applied At'}")
    print("-" * 80)
    for r in rows:
        print(f"{r['version']:>8}  {r['name']:<40}  {r['applied_at']}")


def cmd_ch_pending(args):
    from src.db.clickhouse.schema import migration_pending

    pending_versions = migration_pending()
    if pending_versions:
        print(f"Pending migrations: {pending_versions}")
    else:
        print("All migrations have been applied.")


def cmd_ch_check(args):
    from src.db.clickhouse.schema import migration_check

    ok = migration_check()
    if ok:
        print("All migrations applied.")
        sys.exit(0)
    else:
        print("There are pending migrations!")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="manage.py", description="Data Collector management commands")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("shell", help="Open interactive Python shell with project imports pre-loaded")

    sub.add_parser("bond-sync", help="Sync bond instruments and backfill last 7 days of order books")

    sub.add_parser("sync-instruments", help="Sync all bond instruments from TSETMC to PostgreSQL")

    backfill_parser = sub.add_parser("backfill-order-books", help="Backfill order books for a date range")
    backfill_parser.add_argument("--start", required=True, type=date.fromisoformat, help="Start date (YYYY-MM-DD)")
    backfill_parser.add_argument("--end", required=True, type=date.fromisoformat, help="End date (YYYY-MM-DD)")

    trades_parser = sub.add_parser("backfill-trades", help="Backfill trades for a date range")
    trades_parser.add_argument("--start", required=True, type=date.fromisoformat, help="Start date (YYYY-MM-DD)")
    trades_parser.add_argument("--end", required=True, type=date.fromisoformat, help="End date (YYYY-MM-DD)")

    sub.add_parser("option-sync", help="Sync option instruments and backfill last 7 days of order books + trades")

    sub.add_parser("sync-option-instruments", help="Sync all option instruments from TSETMC MarketWatch to PostgreSQL")

    opt_ob_parser = sub.add_parser("backfill-option-order-books", help="Backfill option order books for a date range")
    opt_ob_parser.add_argument("--start", required=True, type=date.fromisoformat, help="Start date (YYYY-MM-DD)")
    opt_ob_parser.add_argument("--end", required=True, type=date.fromisoformat, help="End date (YYYY-MM-DD)")

    opt_tr_parser = sub.add_parser("backfill-option-trades", help="Backfill option trades for a date range")
    opt_tr_parser.add_argument("--start", required=True, type=date.fromisoformat, help="Start date (YYYY-MM-DD)")
    opt_tr_parser.add_argument("--end", required=True, type=date.fromisoformat, help="End date (YYYY-MM-DD)")

    ch = sub.add_parser("clickhouse", help="ClickHouse migration management")
    ch_sub = ch.add_subparsers(dest="ch_command")

    ch_sub.add_parser("migrate", help="Apply all pending ClickHouse migrations")
    ch_sub.add_parser("downgrade", help="Revert the last ClickHouse migration")
    ch_sub.add_parser("history", help="Show ClickHouse migration history")
    ch_sub.add_parser("pending", help="List pending ClickHouse migrations")
    ch_sub.add_parser("check", help="Exit non-zero if there are pending migrations")

    args = parser.parse_args()

    if args.command == "bond-sync":
        from src.collectors.bond.run_sync import main
        import asyncio
        asyncio.run(main())
    elif args.command == "sync-instruments":
        from src.collectors.bond.instrument_sync import sync_instruments_to_pg
        result = asyncio.run(sync_instruments_to_pg())
        print(f"Synced: {result['synced']}, Errors: {len(result['errors'])}")
        for e in result["errors"]:
            print(f"  {e}")
    elif args.command == "backfill-order-books":
        from src.collectors.bond.order_book_fetcher import (
            backfill_order_books as backfill_for_range,
            get_instrument_codes_active_in_range,
        )
        codes = asyncio.run(get_instrument_codes_active_in_range(args.start, args.end))
        print(f"Found {len(codes)} active bonds in range {args.start} to {args.end}")
        result = asyncio.run(
            backfill_for_range(
                start_date=args.start,
                end_date=args.end,
                instrument_codes=codes,
            )
        )
        print(f"Done. Tried: {result['total_days_tried']}, Rows: {result['total_rows']}, Errors: {len(result['errors'])}")
        for e in result["errors"]:
            print(f"  {e}")
    elif args.command == "backfill-trades":
        from src.collectors.bond.trade_fetcher import backfill_trades as backfill_trades_for_range
        from src.collectors.bond.order_book_fetcher import get_instrument_codes_active_in_range
        codes = asyncio.run(get_instrument_codes_active_in_range(args.start, args.end))
        print(f"Found {len(codes)} active bonds in range {args.start} to {args.end}")
        result = asyncio.run(
            backfill_trades_for_range(
                start_date=args.start,
                end_date=args.end,
                instrument_codes=codes,
            )
        )
        print(f"Done. Tried: {result['total_days_tried']}, Rows: {result['total_rows']}, Errors: {len(result['errors'])}")
        for e in result["errors"]:
            print(f"  {e}")
    elif args.command == "option-sync":
        from src.collectors.option.run_sync import main
        import asyncio
        asyncio.run(main())
    elif args.command == "sync-option-instruments":
        from src.collectors.option.instrument_sync import sync_option_instruments_to_pg
        result = asyncio.run(sync_option_instruments_to_pg())
        print(f"Synced: {result['synced']}, Errors: {len(result['errors'])}")
        for e in result["errors"]:
            print(f"  {e}")
    elif args.command == "backfill-option-order-books":
        from src.collectors.option.order_book_fetcher import (
            backfill_option_order_books as backfill_for_range,
            get_option_codes_active_in_range,
        )
        codes = asyncio.run(get_option_codes_active_in_range(args.start, args.end))
        print(f"Found {len(codes)} active options in range {args.start} to {args.end}")
        result = asyncio.run(
            backfill_for_range(
                start_date=args.start,
                end_date=args.end,
                instrument_codes=codes,
            )
        )
        print(f"Done. Tried: {result['total_days_tried']}, Rows: {result['total_rows']}, Errors: {len(result['errors'])}")
        for e in result["errors"]:
            print(f"  {e}")
    elif args.command == "backfill-option-trades":
        from src.collectors.option.trade_fetcher import backfill_option_trades as backfill_trades_for_range
        from src.collectors.option.order_book_fetcher import get_option_codes_active_in_range
        codes = asyncio.run(get_option_codes_active_in_range(args.start, args.end))
        print(f"Found {len(codes)} active options in range {args.start} to {args.end}")
        result = asyncio.run(
            backfill_trades_for_range(
                start_date=args.start,
                end_date=args.end,
                instrument_codes=codes,
            )
        )
        print(f"Done. Tried: {result['total_days_tried']}, Rows: {result['total_rows']}, Skipped: {result['skipped']}, Errors: {len(result['errors'])}")
        for e in result["errors"]:
            print(f"  {e}")
    elif args.command == "shell":
        cmd_shell(args)
    elif args.command == "clickhouse":
        if args.ch_command == "migrate":
            cmd_ch_migrate(args)
        elif args.ch_command == "downgrade":
            cmd_ch_downgrade(args)
        elif args.ch_command == "history":
            cmd_ch_history(args)
        elif args.ch_command == "pending":
            cmd_ch_pending(args)
        elif args.ch_command == "check":
            cmd_ch_check(args)
        else:
            parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
