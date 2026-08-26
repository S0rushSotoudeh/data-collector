from src.db.clickhouse.ime import IME_PHYSICAL_TRADES_DDL, IME_PHYSICAL_TRADES_TABLE


NEW_ORDER_BY = (
    "producer_code, trade_date, product_symbol, offer_id, contract_type, source_trade_pk"
)
OLD_ORDER_BY = "producer_code, trade_date, product_symbol, offer_id, contract_type"
TEMP_TABLE = f"{IME_PHYSICAL_TRADES_TABLE}_migration_018"


def _sorting_key(client):
    result = client.query(
        "SELECT sorting_key FROM system.tables "
        f"WHERE database = currentDatabase() AND name = '{IME_PHYSICAL_TRADES_TABLE}'"
    )
    return str(result.result_rows[0][0]) if result.result_rows else None


def _ddl_for(table: str, order_by: str) -> str:
    return IME_PHYSICAL_TRADES_DDL.replace(
        f"`{IME_PHYSICAL_TRADES_TABLE}`", f"`{table}`", 1
    ).replace(
        f"ORDER BY ({NEW_ORDER_BY})", f"ORDER BY ({order_by})"
    )


def _rebuild(client, order_by: str):
    current = _sorting_key(client)
    if current is None:
        if order_by == NEW_ORDER_BY:
            client.command(IME_PHYSICAL_TRADES_DDL)
        return
    if current == order_by:
        client.command(f"DROP TABLE IF EXISTS `{TEMP_TABLE}`")
        return

    client.command(f"DROP TABLE IF EXISTS `{TEMP_TABLE}`")
    client.command(_ddl_for(TEMP_TABLE, order_by))
    client.command(
        f"INSERT INTO `{TEMP_TABLE}` SELECT * FROM `{IME_PHYSICAL_TRADES_TABLE}`"
    )
    client.command(
        f"EXCHANGE TABLES `{IME_PHYSICAL_TRADES_TABLE}` AND `{TEMP_TABLE}`"
    )
    client.command(f"DROP TABLE `{TEMP_TABLE}`")


def upgrade(client):
    _rebuild(client, NEW_ORDER_BY)


def downgrade(client):
    _rebuild(client, OLD_ORDER_BY)
