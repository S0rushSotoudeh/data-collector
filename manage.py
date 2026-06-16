"""
Django-like management commands for data-collector.

Usage:
    python manage.py shell      # Open interactive Python shell with project imports
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


def main():
    parser = argparse.ArgumentParser(prog="manage.py", description="Data Collector management commands")
    sub = parser.add_subparsers(dest="command")

    shell = sub.add_parser("shell", help="Open an interactive Python shell with project imports pre-loaded")

    args = parser.parse_args()

    if args.command == "shell":
        cmd_shell(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()