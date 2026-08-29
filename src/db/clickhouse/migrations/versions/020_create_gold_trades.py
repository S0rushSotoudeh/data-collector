from src.db.clickhouse.schema import GOLD_TRADES_TABLE, _GOLD_TRADES_DDL


def upgrade(client):
    client.command(_GOLD_TRADES_DDL)


def downgrade(client):
    client.command(f"DROP TABLE IF EXISTS `{GOLD_TRADES_TABLE}`")
