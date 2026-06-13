import os

from alembic import context
from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel

import src.db.models  # noqa: ensure all models loaded

target_metadata = SQLModel.metadata


def get_url() -> str:
    user = os.getenv("POSTGRES_USER", "dc_user")
    password = os.getenv("POSTGRES_PASSWORD", "dc_pass")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "dc_metadata")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def run_migrations_offline() -> None:
    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with conn.begin():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()