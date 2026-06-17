from src.db.clickhouse.schema import ORDER_BOOK_TABLE, TRADES_TABLE

_OB_TMP = f"`{ORDER_BOOK_TABLE}_tmp`"
_TR_TMP = f"`{TRADES_TABLE}_tmp`"

_OB_DDL_REPLACING = (
    f"CREATE TABLE IF NOT EXISTS {_OB_TMP} ("
    "    instrument_code   String,"
    "    trade_date        Date,"
    "    trade_time        UInt32,"
    "    ref_id            UInt64,"
    "    depth_level       UInt8,"
    "    bid_price         Int64,"
    "    bid_volume        UInt64,"
    "    bid_order_count   UInt32,"
    "    ask_price         Int64,"
    "    ask_volume        UInt64,"
    "    ask_order_count   UInt32,"
    "    data_source       LowCardinality(String),"
    "    ingested_at       DateTime DEFAULT now()"
    ")"
    "ENGINE = ReplacingMergeTree(ingested_at) "
    f"ORDER BY (instrument_code, trade_date, trade_time, depth_level) "
    "PARTITION BY toYYYYMM(trade_date) "
    "TTL ingested_at + INTERVAL 1 YEAR"
)

_TR_DDL_REPLACING = (
    f"CREATE TABLE IF NOT EXISTS {_TR_TMP} ("
    "    instrument_code   String,"
    "    trade_date        Date,"
    "    trade_time        UInt32,"
    "    trade_id          UInt64,"
    "    price             Int64,"
    "    volume            UInt64,"
    "    value             Int64,"
    "    is_canceled       UInt8 DEFAULT 0,"
    "    data_source       LowCardinality(String),"
    "    ingested_at       DateTime DEFAULT now()"
    ")"
    "ENGINE = ReplacingMergeTree(ingested_at) "
    "ORDER BY (instrument_code, trade_date, trade_time, trade_id) "
    "PARTITION BY toYYYYMM(trade_date) "
    "TTL ingested_at + INTERVAL 1 YEAR"
)


def _swap_table(client, original: str, tmp: str):
    client.command(f"DROP TABLE IF EXISTS `{original}`")
    client.command(f"RENAME TABLE `{tmp}` TO `{original}`")


_OB_DDL_MERGETREE = (
    f"CREATE TABLE IF NOT EXISTS {_OB_TMP} ("
    "    instrument_code   String,"
    "    trade_date        Date,"
    "    trade_time        UInt32,"
    "    ref_id            UInt64,"
    "    depth_level       UInt8,"
    "    bid_price         Int64,"
    "    bid_volume        UInt64,"
    "    bid_order_count   UInt32,"
    "    ask_price         Int64,"
    "    ask_volume        UInt64,"
    "    ask_order_count   UInt32,"
    "    data_source       LowCardinality(String),"
    "    ingested_at       DateTime DEFAULT now()"
    ")"
    "ENGINE = MergeTree "
    "ORDER BY (instrument_code, trade_date, trade_time, depth_level) "
    "PARTITION BY toYYYYMM(trade_date) "
    "TTL ingested_at + INTERVAL 1 YEAR"
)

_TR_DDL_MERGETREE = (
    f"CREATE TABLE IF NOT EXISTS {_TR_TMP} ("
    "    instrument_code   String,"
    "    trade_date        Date,"
    "    trade_time        UInt32,"
    "    trade_id          UInt64,"
    "    price             Int64,"
    "    volume            UInt64,"
    "    value             Int64,"
    "    is_canceled       UInt8 DEFAULT 0,"
    "    data_source       LowCardinality(String),"
    "    ingested_at       DateTime DEFAULT now()"
    ")"
    "ENGINE = MergeTree "
    "ORDER BY (instrument_code, trade_date, trade_time, trade_id) "
    "PARTITION BY toYYYYMM(trade_date) "
    "TTL ingested_at + INTERVAL 1 YEAR"
)


def upgrade(client):
    # bond_order_book: MergeTree -> ReplacingMergeTree
    client.command(_OB_DDL_REPLACING)
    client.command(
        f"INSERT INTO {_OB_TMP} SELECT * FROM `{ORDER_BOOK_TABLE}`"
    )
    _swap_table(client, ORDER_BOOK_TABLE, ORDER_BOOK_TABLE + "_tmp")

    # bond_trades: MergeTree -> ReplacingMergeTree
    client.command(_TR_DDL_REPLACING)
    client.command(
        f"INSERT INTO {_TR_TMP} SELECT * FROM `{TRADES_TABLE}`"
    )
    _swap_table(client, TRADES_TABLE, TRADES_TABLE + "_tmp")


def downgrade(client):
    # bond_order_book: ReplacingMergeTree -> MergeTree
    client.command(_OB_DDL_MERGETREE)
    client.command(
        f"INSERT INTO {_OB_TMP} SELECT * FROM `{ORDER_BOOK_TABLE}`"
    )
    _swap_table(client, ORDER_BOOK_TABLE, ORDER_BOOK_TABLE + "_tmp")

    # bond_trades: ReplacingMergeTree -> MergeTree
    client.command(_TR_DDL_MERGETREE)
    client.command(
        f"INSERT INTO {_TR_TMP} SELECT * FROM `{TRADES_TABLE}`"
    )
    _swap_table(client, TRADES_TABLE, TRADES_TABLE + "_tmp")
