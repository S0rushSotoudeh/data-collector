"""
Django-like management commands for data-collector.

Usage:
python manage.py shell                    # Open interactive Python shell
    python manage.py bond-sync                # Sync bonds + backfill last 7 days of order books
    python manage.py clickhouse migrate       # Apply all pending ClickHouse migrations
    python manage.py clickhouse downgrade      # Revert last ClickHouse migration
    python manage.py clickhouse history        # Show ClickHouse migration history
    python manage.py clickhouse pending        # List pending ClickHouse migrations
    python manage.py clickhouse check          # Exit non-zero if pending migrations exist
"""

import os
import sys
import argparse

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
    from src.db.models import BondInstrument
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
