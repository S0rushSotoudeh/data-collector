"""Run-scoped gold consensus output and immutable source event snapshots.

Versions 019/020 exist in deployed databases outside this checkout; do not
reuse their numbers for a different schema.
"""


def upgrade(client):
    client.command("""CREATE TABLE IF NOT EXISTS gold_kalman_inputs (
        dataset_id UUID, session_index UInt16, instrument_code String,
        available_at Float64, quote_time Float64, sequence UInt64,
        bid Float64, ask Float64, bid_qty Float64, ask_qty Float64, phase UInt8
    ) ENGINE = MergeTree ORDER BY (dataset_id, session_index, instrument_code, available_at, sequence)""")
    common = "run_id UUID, method LowCardinality(String), range_name LowCardinality(String), decision_time DateTime64(3, 'Asia/Tehran'), calibration_id UUID, "
    definitions = {
        "scores": ("instrument_code String, microprice Float64, midpoint Float64, bid Float64, ask Float64, "
                   "fair_price Float64, z_score Float64, residual Float64, benchmark_variance Float64, "
                   "mispricing_bps Float64, cheap_edge_bps Float64, rich_edge_bps Float64, "
                   "spread_bps Float64, imbalance Float64, quote_age Float64, coverage UInt16, persistence UInt32, alert UInt8", ", instrument_code"),
        "market": ("factor Nullable(Float64), factor_sigma Nullable(Float64), coverage UInt16, "
                   "dispersion Nullable(Float64), max_abs_z Nullable(Float64), ready UInt8, reason String, "
                   "symbols Array(String), midpoints Array(Float64)", ""),
        "outcomes": ("instrument_code String, horizon Float64, available UInt8, reason String, "
                     "relative_return Nullable(Float64), recovery_log_bps Nullable(Float64), "
                     "gap_reduction_log_bps Nullable(Float64), micro_error_log_bps Nullable(Float64), "
                     "mid_error_log_bps Nullable(Float64)", ", instrument_code"),
    }
    for name, (fields, suffix) in definitions.items():
        client.command(f"CREATE TABLE IF NOT EXISTS gold_kalman_{name} ({common}{fields}) "
                       "ENGINE = ReplacingMergeTree ORDER BY (run_id, method, range_name, decision_time"
                       f"{suffix}) PARTITION BY toYYYYMM(decision_time)")


def downgrade(client):
    for name in ("outcomes", "market", "scores", "inputs"):
        client.command(f"DROP TABLE IF EXISTS gold_kalman_{name}")
