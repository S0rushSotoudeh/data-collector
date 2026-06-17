from alembic import context
from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel

import src.db.config as db_config
import src.db.models  # noqa: ensure all models loaded

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(url=db_config.get_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(db_config.get_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with conn.begin():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()