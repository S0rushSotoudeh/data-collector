"""Two-year option/stock raw retention and permanent option analytics."""


def upgrade(client):
    for table in ("option_order_book", "option_trades", "stock_order_book", "stock_trades"):
        client.command(f"ALTER TABLE `{table}` MODIFY TTL ingested_at + INTERVAL 2 YEAR")
    client.command("""
    CREATE TABLE IF NOT EXISTS option_contract_daily (
      trade_date Date, instrument_code String, underlying_instrument_code String,
      option_type LowCardinality(String), strike Float64, expiry_date Date,
      trade_count UInt64, traded_volume UInt64, traded_value Float64, vwap Nullable(Float64),
      spread_p25 Nullable(Float64), spread_p50 Nullable(Float64), spread_p75 Nullable(Float64),
      bid_depth Float64, ask_depth Float64, two_sided_ratio Float64,
      activity_score Float64, liquidity_score Float64, quality_flags Array(String), computed_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(computed_at) PARTITION BY toYYYYMM(trade_date)
    ORDER BY (trade_date, underlying_instrument_code, instrument_code)
    """)
    client.command("""
    CREATE TABLE IF NOT EXISTS option_pair_daily (
      trade_date Date, underlying_instrument_code String, call_instrument_code String,
      put_instrument_code String, strike Float64, expiry_date Date, mapping_status LowCardinality(String),
      trade_count UInt64, traded_value Float64, quote_availability Float64, bid_depth Float64,
      ask_depth Float64, activity_score Float64, pilot_eligible UInt8, quality_flags Array(String), computed_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(computed_at) PARTITION BY toYYYYMM(trade_date)
    ORDER BY (trade_date, underlying_instrument_code, expiry_date, strike)
    """)
    client.command("""
    CREATE TABLE IF NOT EXISTS iv_surface_runs (
      run_id UUID, underlying_instrument_code String, start_date Date, end_date Date,
      session_start String, session_end String, interval_seconds UInt8, max_quote_age_seconds UInt32,
      forward_source LowCardinality(String), rate_source LowCardinality(String), pricing_convention_id UUID,
      pricing_convention_version String, model_version LowCardinality(String), config_json String,
      status LowCardinality(String), target_snapshot_count UInt64, completed_snapshot_count UInt64,
      point_count UInt64, fit_count UInt64, warning_count UInt64, quality_summary String, error String,
      created_at DateTime64(3), updated_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(updated_at) ORDER BY run_id
    """)
    client.command("""
    CREATE TABLE IF NOT EXISTS option_iv_points (
      run_id UUID, snapshot_time DateTime64(3, 'Asia/Tehran'), trade_date Date,
      underlying_instrument_code String, instrument_code String, option_type LowCardinality(String),
      side LowCardinality(String), strike Float64, expiry_date Date, ttm_years Float64,
      forward_lower Nullable(Float64), forward_upper Nullable(Float64), forward Nullable(Float64),
      rate Nullable(Float64), rate_source LowCardinality(String), price Nullable(Float64), iv Nullable(Float64),
      vega Nullable(Float64), depth UInt64, quote_time Nullable(DateTime64(3, 'Asia/Tehran')),
      quote_age_seconds Nullable(UInt32), weight Nullable(Float64), rejection_reason String, created_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(created_at) PARTITION BY toYYYYMM(trade_date)
    ORDER BY (run_id, snapshot_time, expiry_date, side, strike, instrument_code)
    """)
    client.command("""
    CREATE TABLE IF NOT EXISTS orc_wing_fits (
      run_id UUID, snapshot_time DateTime64(3, 'Asia/Tehran'), trade_date Date,
      underlying_instrument_code String, expiry_date Date, side LowCardinality(String), forward Float64,
      ttm_years Float64, vc Nullable(Float64), sc Nullable(Float64), pc Nullable(Float64), cc Nullable(Float64),
      dc Nullable(Float64), uc Nullable(Float64), dsm Float64, usm Float64, rmse Nullable(Float64),
      point_count UInt16, converged UInt8, quality_flags Array(String), created_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(created_at) PARTITION BY toYYYYMM(trade_date)
    ORDER BY (run_id, snapshot_time, expiry_date, side)
    """)


def downgrade(client):
    for table in ("orc_wing_fits", "option_iv_points", "iv_surface_runs", "option_pair_daily", "option_contract_daily"):
        client.command(f"DROP TABLE IF EXISTS `{table}`")
    for table in ("option_order_book", "option_trades", "stock_order_book", "stock_trades"):
        client.command(f"ALTER TABLE `{table}` MODIFY TTL ingested_at + INTERVAL 1 YEAR")
