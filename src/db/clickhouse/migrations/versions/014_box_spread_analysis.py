"""Permanent, normalized box-spread snapshots and pricing scenarios."""


def upgrade(client):
    client.command("""
    CREATE TABLE IF NOT EXISTS box_spread_snapshots (
      run_id UUID, trade_date Date, snapshot_time DateTime64(3, 'Asia/Tehran'),
      underlying_instrument_code String, expiry_date Date, lower_strike Float64, upper_strike Float64,
      box_width Float64, target_boxes UInt64, multiplier UInt32, tick_size Float64,
      c1_instrument_code String, c1_source_time Nullable(DateTime64(3, 'Asia/Tehran')), c1_age_seconds Nullable(UInt32),
      c1_best_bid Nullable(Float64), c1_best_ask Nullable(Float64), c1_bid_total_volume UInt64, c1_ask_total_volume UInt64, c1_bid_order_count UInt32, c1_ask_order_count UInt32,
      c2_instrument_code String, c2_source_time Nullable(DateTime64(3, 'Asia/Tehran')), c2_age_seconds Nullable(UInt32),
      c2_best_bid Nullable(Float64), c2_best_ask Nullable(Float64), c2_bid_total_volume UInt64, c2_ask_total_volume UInt64, c2_bid_order_count UInt32, c2_ask_order_count UInt32,
      p1_instrument_code String, p1_source_time Nullable(DateTime64(3, 'Asia/Tehran')), p1_age_seconds Nullable(UInt32),
      p1_best_bid Nullable(Float64), p1_best_ask Nullable(Float64), p1_bid_total_volume UInt64, p1_ask_total_volume UInt64, p1_bid_order_count UInt32, p1_ask_order_count UInt32,
      p2_instrument_code String, p2_source_time Nullable(DateTime64(3, 'Asia/Tehran')), p2_age_seconds Nullable(UInt32),
      p2_best_bid Nullable(Float64), p2_best_ask Nullable(Float64), p2_bid_total_volume UInt64, p2_ask_total_volume UInt64, p2_bid_order_count UInt32, p2_ask_order_count UInt32,
      cross_leg_skew_seconds Nullable(UInt32), ttm_years Float64, benchmark_rate Nullable(Float64), benchmark_source LowCardinality(String),
      curve_time Nullable(DateTime64(3, 'Asia/Tehran')), curve_age_seconds Nullable(UInt32),
      curve_beta0 Nullable(Float64), curve_beta1 Nullable(Float64), curve_beta2 Nullable(Float64), curve_lambda Nullable(Float64),
      curve_rmse Nullable(Float64), curve_n_bonds Nullable(UInt16), curve_converged Nullable(UInt8),
      quality_status LowCardinality(String), quality_reasons Array(String), warnings Array(String),
      calculation_version LowCardinality(String), calculated_at DateTime64(3)
    ) ENGINE = MergeTree PARTITION BY toYYYYMM(trade_date)
    ORDER BY (run_id, trade_date, snapshot_time)
    """)
    client.command("""
    CREATE TABLE IF NOT EXISTS box_spread_pricings (
      run_id UUID, trade_date Date, snapshot_time DateTime64(3, 'Asia/Tehran'),
      direction LowCardinality(String), execution_mode LowCardinality(String), maker_leg LowCardinality(String), maker_side LowCardinality(String),
      target_boxes UInt64, capacity_boxes UInt64, feasible UInt8,
      signed_entry_cost_per_share Float64, entry_debit_per_share Nullable(Float64), entry_credit_per_share Nullable(Float64),
      entry_debit_per_contract Nullable(Float64), entry_credit_per_contract Nullable(Float64), total_entry_debit Nullable(Float64), total_entry_credit Nullable(Float64),
      opening_fee_per_share Float64, opening_fee_per_contract Float64, settlement_cost_per_contract Float64,
      terminal_cashflow_per_share Float64, terminal_cashflow_per_contract Float64, total_terminal_cashflow Float64,
      implied_rate Nullable(Float64), benchmark_rate Float64, benchmark_spread_bps Nullable(Float64), threshold_bps Float64,
      opportunity UInt8, review_anomaly UInt8, classification LowCardinality(String), current_maker_price Nullable(Float64),
      queue_ahead_volume Nullable(UInt64), hedge_signed_cost_per_share Nullable(Float64), target_signed_cost_per_share Nullable(Float64),
      safe_maker_boundary Nullable(Float64), suggested_maker_price Nullable(Float64), headroom Nullable(Float64),
      quality_reasons Array(String), calculation_version LowCardinality(String), calculated_at DateTime64(3)
    ) ENGINE = MergeTree PARTITION BY toYYYYMM(trade_date)
    ORDER BY (run_id, trade_date, snapshot_time, direction, execution_mode, maker_leg)
    """)


def downgrade(client):
    client.command("DROP TABLE IF EXISTS `box_spread_pricings`")
    client.command("DROP TABLE IF EXISTS `box_spread_snapshots`")
