from src.db.clickhouse.parity import RUNS_DDL, RUNS_TABLE, SNAPSHOTS_DDL, SNAPSHOTS_TABLE


def upgrade(client):
    client.command(RUNS_DDL)
    client.command(SNAPSHOTS_DDL)


def downgrade(client):
    client.command(f"DROP TABLE IF EXISTS `{SNAPSHOTS_TABLE}`")
    client.command(f"DROP TABLE IF EXISTS `{RUNS_TABLE}`")
