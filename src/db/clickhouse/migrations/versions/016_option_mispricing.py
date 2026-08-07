"""Dedicated date-driven option mispricing analysis tables."""


def upgrade(client):
    client.command("""
    CREATE TABLE IF NOT EXISTS option_mispricing_universe (
      run_id UUID, trade_date Date, instrument_code String, underlying_instrument_code String,
      option_type LowCardinality(String), strike Nullable(Float64), expiry_date Nullable(Date),
      listing_date Nullable(Date), quote_count UInt64, two_sided_quote_count UInt64,
      first_quote_time UInt32, last_quote_time UInt32, group_strike_count UInt16,
      group_call_count UInt16, group_put_count UInt16, eligible UInt8, eligibility_reasons Array(String),
      model_version LowCardinality(String), configuration_version LowCardinality(String),
      pricing_convention_id UUID, pricing_convention_version String, frozen_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(frozen_at) PARTITION BY toYYYYMM(trade_date)
    ORDER BY (run_id, underlying_instrument_code, ifNull(expiry_date, toDate('1970-01-01')),
              ifNull(strike, 0), option_type, instrument_code)
    """)
    client.command("""
    CREATE TABLE IF NOT EXISTS option_mispricing_fits (
      run_id UUID, trade_date Date, snapshot_time DateTime64(3, 'Asia/Tehran'),
      underlying_instrument_code String, expiry_date Date, forward_lower Nullable(Float64),
      forward_upper Nullable(Float64), forward Nullable(Float64), rate Nullable(Float64),
      rate_source LowCardinality(String), ttm_years Float64, vc Nullable(Float64), sc Nullable(Float64),
      pc Nullable(Float64), cc Nullable(Float64), dc Nullable(Float64), uc Nullable(Float64),
      dsm Float64, usm Float64, rmse Nullable(Float64), point_count UInt16, used_point_count UInt16,
      excluded_point_count UInt16, fit_passes UInt8, converged UInt8,
      excluded_instrument_codes Array(String), excluded_reasons Array(String),
      quality_status LowCardinality(String), quality_flags Array(String), created_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(created_at) PARTITION BY toYYYYMM(trade_date)
    ORDER BY (run_id, underlying_instrument_code, expiry_date, snapshot_time)
    """)
    client.command("""
    CREATE TABLE IF NOT EXISTS option_mispricing_observations (
      run_id UUID, trade_date Date, snapshot_time DateTime64(3, 'Asia/Tehran'),
      underlying_instrument_code String, instrument_code String, option_type LowCardinality(String),
      strike Float64, expiry_date Date, bid_price Nullable(Float64), midpoint_price Nullable(Float64),
      fair_price Nullable(Float64), ask_price Nullable(Float64), fair_iv Nullable(Float64),
      bid_distance Nullable(Float64), ask_distance Nullable(Float64), midpoint_distance Nullable(Float64),
      bid_distance_bps Nullable(Float64), ask_distance_bps Nullable(Float64),
      midpoint_distance_bps Nullable(Float64), forward Nullable(Float64), rate Nullable(Float64),
      rate_source LowCardinality(String), depth UInt64, bid_depth UInt64, ask_depth UInt64,
      quote_time Nullable(DateTime64(3, 'Asia/Tehran')), quote_age_seconds Nullable(UInt32),
      fit_rmse Nullable(Float64), quality_status LowCardinality(String), rejection_reason String,
      created_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(created_at) PARTITION BY toYYYYMM(trade_date)
    ORDER BY (run_id, underlying_instrument_code, expiry_date, snapshot_time, strike, option_type, instrument_code)
    """)
    client.command("""
    CREATE TABLE IF NOT EXISTS option_mispricing_rankings (
      run_id UUID, trade_date Date, underlying_instrument_code String, valid_contract_count UInt32,
      valid_expiry_count UInt16, valid_snapshot_count UInt32, total_snapshot_count UInt32,
      snapshot_coverage Float64, median_abs_midpoint_bps Nullable(Float64),
      p90_abs_midpoint_bps Nullable(Float64), largest_bid_deviation_bps Nullable(Float64),
      largest_ask_deviation_bps Nullable(Float64), outside_25_count UInt64, outside_25_share Float64,
      outside_50_count UInt64, outside_50_share Float64, outside_100_count UInt64,
      outside_100_share Float64, affected_contract_count UInt32, excluded_observation_count UInt64,
      quality_warnings Array(String), created_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(created_at) PARTITION BY toYYYYMM(trade_date)
    ORDER BY (run_id, underlying_instrument_code)
    """)


def downgrade(client):
    for table in (
        "option_mispricing_rankings", "option_mispricing_observations",
        "option_mispricing_fits", "option_mispricing_universe",
    ):
        client.command(f"DROP TABLE IF EXISTS `{table}`")
