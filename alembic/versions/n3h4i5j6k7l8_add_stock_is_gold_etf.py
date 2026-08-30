"""add gold ETF flag to stock instruments

Revision ID: n3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa


revision = "n3h4i5j6k7l8"
down_revision = "l2g3h4i5j6k7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_instruments",
        sa.Column("is_gold_etf", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("stock_instruments", "is_gold_etf")
