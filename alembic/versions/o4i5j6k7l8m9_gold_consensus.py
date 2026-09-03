"""Immutable gold replay inputs and calibration versions."""
from alembic import op
import sqlalchemy as sa

revision = "o4i5j6k7l8m9"
down_revision = "n3h4i5j6k7l8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("gold_kalman_datasets",
        sa.Column("dataset_id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("error", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("gold_kalman_calibrations",
        sa.Column("calibration_id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("session_open", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False))
    op.create_index("ix_gold_kalman_calibrations_run_id", "gold_kalman_calibrations", ["run_id"])


def downgrade():
    op.drop_table("gold_kalman_calibrations")
    op.drop_table("gold_kalman_datasets")
