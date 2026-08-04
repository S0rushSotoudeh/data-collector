"""add collection runs and option pricing conventions

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-03 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_data_collection_runs_dataset", "data_collection_runs", ["dataset"])
    op.create_index("ix_data_collection_runs_status", "data_collection_runs", ["status"])
    op.create_index("idx_collection_dataset_dates", "data_collection_runs", ["dataset", "start_date", "end_date"])
    op.create_table(
        "option_pricing_conventions",
        sa.Column("convention_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("contract_family", sa.String(80), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("exercise_style", sa.String(24), nullable=False),
        sa.Column("settlement_style", sa.String(40), nullable=False),
        sa.Column("multiplier", sa.Integer(), nullable=False),
        sa.Column("tick_size", sa.Float(), nullable=False),
        sa.Column("price_unit", sa.String(24), nullable=False),
        sa.Column("black76_compatible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reference_source", sa.String(500), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approver", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("convention_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_option_pricing_conventions_contract_family", "option_pricing_conventions", ["contract_family"])
    op.create_index("idx_pricing_convention_effective", "option_pricing_conventions", ["contract_family", "effective_from", "effective_to"])


def downgrade() -> None:
    op.drop_table("option_pricing_conventions")
    op.drop_table("data_collection_runs")
