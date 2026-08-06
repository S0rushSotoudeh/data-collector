"""Add parity-v3 YTM and invested-capital metrics without rewriting v2 data."""

from src.db.clickhouse.parity import RUNS_TABLE, SNAPSHOTS_TABLE


STRATEGIES = ("make_call_ask", "make_put_bid", "make_underlying_bid")
STRATEGY_FIELDS = (
    "target_boundary",
    "capital_per_share",
    "capital_per_contract",
    "total_capital",
    "expiry_profit_per_share",
    "expiry_profit_per_contract",
    "total_expiry_profit",
    "holding_return",
    "ytm",
    "ytm_spread_bps",
)


def upgrade(client):
    client.command(
        f"ALTER TABLE `{RUNS_TABLE}` ADD COLUMN IF NOT EXISTS "
        "minimum_ytm_spread_bps Nullable(Float64)"
    )
    for field in ("target_ytm", "target_capital_per_share"):
        client.command(
            f"ALTER TABLE `{SNAPSHOTS_TABLE}` ADD COLUMN IF NOT EXISTS "
            f"{field} Nullable(Float64)"
        )
    for strategy in STRATEGIES:
        for field in STRATEGY_FIELDS:
            client.command(
                f"ALTER TABLE `{SNAPSHOTS_TABLE}` ADD COLUMN IF NOT EXISTS "
                f"{strategy}_{field} Nullable(Float64)"
            )


def downgrade(client):
    for strategy in STRATEGIES:
        for field in reversed(STRATEGY_FIELDS):
            client.command(
                f"ALTER TABLE `{SNAPSHOTS_TABLE}` DROP COLUMN IF EXISTS "
                f"{strategy}_{field}"
            )
    for field in ("target_capital_per_share", "target_ytm"):
        client.command(
            f"ALTER TABLE `{SNAPSHOTS_TABLE}` DROP COLUMN IF EXISTS {field}"
        )
    client.command(
        f"ALTER TABLE `{RUNS_TABLE}` DROP COLUMN IF EXISTS minimum_ytm_spread_bps"
    )
