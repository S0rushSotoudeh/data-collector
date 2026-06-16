from src.db.clickhouse.migrations.manager import MIGRATIONS_TABLE

_MIGRATIONS_TABLE_DDL = (
    f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} ("
    "    version UInt16,"
    "    name String,"
    "    applied_at DateTime DEFAULT now()"
    ") ENGINE = MergeTree "
    "ORDER BY version"
)


def upgrade(client):
    client.command(_MIGRATIONS_TABLE_DDL)


def downgrade(client):
    client.command(f"DROP TABLE IF EXISTS {MIGRATIONS_TABLE}")