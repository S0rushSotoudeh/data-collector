"""Add additive depth-aware parity-v5 fields without rewriting history."""

from src.db.clickhouse.parity import SNAPSHOTS_TABLE


def upgrade(client):
    columns = {
        "target_package_count": "UInt64 DEFAULT 1", "cross_leg_skew_seconds": "Nullable(UInt32)",
        "stock_bid_depth_volume": "UInt64 DEFAULT 0", "stock_ask_depth_volume": "UInt64 DEFAULT 0",
        "call_bid_depth_volume": "UInt64 DEFAULT 0", "call_ask_depth_volume": "UInt64 DEFAULT 0",
        "put_bid_depth_volume": "UInt64 DEFAULT 0", "put_ask_depth_volume": "UInt64 DEFAULT 0",
        "direct_take_capital_per_share": "Nullable(Float64)", "direct_take_capital_per_contract": "Nullable(Float64)",
        "direct_take_total_capital": "Nullable(Float64)", "direct_take_opening_fee": "Nullable(Float64)",
        "direct_take_expiry_profit_per_share": "Nullable(Float64)", "direct_take_expiry_profit_per_contract": "Nullable(Float64)",
        "direct_take_total_expiry_profit": "Nullable(Float64)", "direct_take_holding_return": "Nullable(Float64)",
        "direct_take_ytm": "Nullable(Float64)", "direct_take_ytm_spread_bps": "Nullable(Float64)",
        "direct_take_capacity": "UInt64 DEFAULT 0", "direct_take_opportunity": "UInt8 DEFAULT 0",
    }
    for strategy in ("make_call_ask", "make_put_bid", "make_underlying_bid"):
        columns[f"{strategy}_quoteable"] = "UInt8 DEFAULT 0"
        columns[f"{strategy}_queue_ahead_volume"] = "UInt64 DEFAULT 0"
    for name, kind in columns.items():
        client.command(f"ALTER TABLE `{SNAPSHOTS_TABLE}` ADD COLUMN IF NOT EXISTS {name} {kind}")


def downgrade(client):
    names = [
        "target_package_count", "cross_leg_skew_seconds", "stock_bid_depth_volume", "stock_ask_depth_volume",
        "call_bid_depth_volume", "call_ask_depth_volume", "put_bid_depth_volume", "put_ask_depth_volume",
        "direct_take_capital_per_share", "direct_take_capital_per_contract", "direct_take_total_capital",
        "direct_take_opening_fee", "direct_take_expiry_profit_per_share", "direct_take_expiry_profit_per_contract",
        "direct_take_total_expiry_profit", "direct_take_holding_return", "direct_take_ytm",
        "direct_take_ytm_spread_bps", "direct_take_capacity", "direct_take_opportunity",
        *[f"{s}_{f}" for s in ("make_call_ask", "make_put_bid", "make_underlying_bid") for f in ("quoteable", "queue_ahead_volume")],
    ]
    for name in reversed(names):
        client.command(f"ALTER TABLE `{SNAPSHOTS_TABLE}` DROP COLUMN IF EXISTS {name}")
