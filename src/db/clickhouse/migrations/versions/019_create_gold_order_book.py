from src.db.clickhouse.schema import GOLD_ORDER_BOOK_TABLE, _GOLD_ORDER_BOOK_DDL


def upgrade(client):
    client.command(_GOLD_ORDER_BOOK_DDL)


def downgrade(client):
    client.command(f"DROP TABLE IF EXISTS `{GOLD_ORDER_BOOK_TABLE}`")
