from src.db.clickhouse.schema import STOCK_ORDER_BOOK_TABLE

_STOCK_ORDER_BOOK_DDL = (
    f"CREATE TABLE IF NOT EXISTS `{STOCK_ORDER_BOOK_TABLE}` ("
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
    "ORDER BY (instrument_code, trade_date, trade_time, depth_level) "
    "PARTITION BY toYYYYMM(trade_date) "
    "TTL ingested_at + INTERVAL 1 YEAR"
)


def upgrade(client):
    client.command(_STOCK_ORDER_BOOK_DDL)


def downgrade(client):
    client.command(f"DROP TABLE IF EXISTS `{STOCK_ORDER_BOOK_TABLE}`")
