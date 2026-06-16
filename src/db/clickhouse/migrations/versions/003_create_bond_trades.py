from src.db.clickhouse.schema import TRADES_TABLE

_TRADES_DDL = (
    f"CREATE TABLE IF NOT EXISTS `{TRADES_TABLE}` ("
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
    client.command(_TRADES_DDL)


def downgrade(client):
    client.command(f"DROP TABLE IF EXISTS `{TRADES_TABLE}`")