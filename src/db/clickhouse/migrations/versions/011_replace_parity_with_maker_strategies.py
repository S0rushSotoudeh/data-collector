"""Destructively replace the v1 two-direction parity schema with parity-v2."""

from src.db.clickhouse.parity import RUNS_DDL, RUNS_TABLE, SNAPSHOTS_DDL, SNAPSHOTS_TABLE


def upgrade(client):
    # Intentional data loss: v1 fields have no compatible interpretation in v2.
    client.command(f"DROP TABLE IF EXISTS `{SNAPSHOTS_TABLE}`")
    client.command(f"DROP TABLE IF EXISTS `{RUNS_TABLE}`")
    client.command(RUNS_DDL)
    client.command(SNAPSHOTS_DDL)


def downgrade(client):
    raise RuntimeError("Migration 011 is intentionally irreversible: parity v1 data was discarded")
