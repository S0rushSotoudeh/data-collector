"""standardize operational run tracking

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa


revision = "h8c9d0e1f2g3"
down_revision = "g7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_runs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("family", sa.String(40), nullable=False),
        sa.Column("run_type", sa.String(96), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("trigger", sa.String(24), nullable=False, server_default="manual"),
        sa.Column("celery_task_id", sa.String(80), nullable=True),
        sa.Column("target", sa.String(160), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("progress_current", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("run_id"),
    )
    for column in ("family", "run_type", "status", "trigger", "celery_task_id", "target", "start_date", "end_date"):
        op.create_index(f"ix_operation_runs_{column}", "operation_runs", [column])
    op.create_index("idx_operation_runs_family_created", "operation_runs", ["family", "created_at"])
    op.create_index("idx_operation_runs_type_dates", "operation_runs", ["run_type", "start_date", "end_date"])

    op.execute("""
        INSERT INTO operation_runs (
            run_id, family, run_type, status, trigger, target, start_date, end_date,
            config, result, output_count, error, created_at, started_at, completed_at, updated_at
        )
        SELECT run_id, 'collection', 'collection.' || dataset, status, 'manual', dataset,
               start_date, end_date, json_build_object('dataset', dataset), details,
               row_count, error, created_at, started_at, completed_at,
               COALESCE(completed_at, started_at, created_at, now())
        FROM data_collection_runs
        ON CONFLICT (run_id) DO NOTHING
    """)
    op.drop_table("data_collection_runs")


def downgrade() -> None:
    op.create_table(
        "data_collection_runs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("dataset", sa.String(64), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.execute("""
        INSERT INTO data_collection_runs
            (run_id, dataset, start_date, end_date, status, row_count, error, details,
             created_at, started_at, completed_at)
        SELECT run_id, COALESCE(target, run_type), start_date, end_date, status,
               output_count, error, result, created_at, started_at, completed_at
        FROM operation_runs
        WHERE family = 'collection' AND start_date IS NOT NULL AND end_date IS NOT NULL
    """)
    op.drop_table("operation_runs")
