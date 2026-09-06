TABLE = "deposit_certificate_order_book_stream"


def upgrade(client):
    client.command(f"""CREATE TABLE IF NOT EXISTS `{TABLE}` (
        event_id FixedString(64),
        book_hash FixedString(64),
        contract_id UInt32,
        symbol LowCardinality(String),
        provider_event_at DateTime64(3, 'Asia/Tehran'),
        received_at DateTime64(3, 'Asia/Tehran'),
        redis_id String,
        bid_price_1 Int64, bid_volume_1 UInt64,
        bid_price_2 Int64, bid_volume_2 UInt64,
        bid_price_3 Int64, bid_volume_3 UInt64,
        ask_price_1 Int64, ask_volume_1 UInt64,
        ask_price_2 Int64, ask_volume_2 UInt64,
        ask_price_3 Int64, ask_volume_3 UInt64,
        ingested_at DateTime64(3, 'Asia/Tehran') DEFAULT now64(3)
    ) ENGINE = ReplacingMergeTree(ingested_at)
    ORDER BY (symbol, provider_event_at, event_id)
    PARTITION BY toYYYYMM(provider_event_at)
    TTL provider_event_at + INTERVAL 90 DAY DELETE""")


def downgrade(client):
    client.command(f"DROP TABLE IF EXISTS `{TABLE}`")
