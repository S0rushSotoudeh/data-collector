"""add effective-dated option fee schedules

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa


revision = "j0e1f2g3h4i5"
down_revision = "i9d0e1f2g3h4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "option_fee_schedules",
        sa.Column("fee_schedule_id", sa.Uuid(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("buy_rate", sa.Numeric(12, 8), nullable=False),
        sa.Column("sell_rate", sa.Numeric(12, 8), nullable=False),
        sa.Column("settlement_cost_per_contract", sa.Numeric(18, 4), nullable=True),
        sa.Column("source", sa.String(500), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("fee_schedule_id"),
        sa.UniqueConstraint("market", "effective_from", name="uq_option_fee_market_effective_from"),
        sa.CheckConstraint("market IN ('tse', 'ifb')", name="ck_option_fee_market"),
        sa.CheckConstraint("buy_rate >= 0 AND buy_rate < 1", name="ck_option_fee_buy_rate"),
        sa.CheckConstraint("sell_rate >= 0 AND sell_rate < 1", name="ck_option_fee_sell_rate"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_option_fee_effective_range",
        ),
        sa.CheckConstraint(
            "settlement_cost_per_contract IS NULL OR settlement_cost_per_contract >= 0",
            name="ck_option_fee_settlement_cost",
        ),
    )
    op.create_index("ix_option_fee_schedules_market", "option_fee_schedules", ["market"])
    op.create_index("ix_option_fee_schedules_effective_from", "option_fee_schedules", ["effective_from"])
    op.create_index("ix_option_fee_schedules_effective_to", "option_fee_schedules", ["effective_to"])
    op.create_index(
        "idx_option_fee_market_effective",
        "option_fee_schedules",
        ["market", "effective_from", "effective_to"],
    )
    op.execute(
        """
        INSERT INTO option_fee_schedules (
            fee_schedule_id, market, effective_from, buy_rate, sell_rate, source, notes
        ) VALUES
            ('86b7bb2b-250e-4c55-bca8-21c8b6a96701', 'tse', DATE '2026-06-16',
             0.00103000, 0.00103000, 'doc/quant/fees.md',
             'Editable default. Settlement cost is unknown, so results are pre-settlement.'),
            ('86b7bb2b-250e-4c55-bca8-21c8b6a96702', 'ifb', DATE '2026-06-16',
             0.00102000, 0.00103000, 'doc/quant/fees.md',
             'Editable default. Settlement cost is unknown, so results are pre-settlement.')
        """
    )


def downgrade() -> None:
    op.drop_table("option_fee_schedules")
