from src.db.clickhouse.ime import IME_PHYSICAL_TRADES_DDL, IME_PHYSICAL_TRADES_TABLE


def upgrade(client):
    client.command(IME_PHYSICAL_TRADES_DDL)


def downgrade(client):
    client.command(f"DROP TABLE IF EXISTS `{IME_PHYSICAL_TRADES_TABLE}`")
