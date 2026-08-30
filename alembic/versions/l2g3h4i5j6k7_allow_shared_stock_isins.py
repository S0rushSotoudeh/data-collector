"""allow distinct stock instruments to share an ISIN

Revision ID: l2g3h4i5j6k7
Revises: j0e1f2g3h4i5
Create Date: 2026-08-30
"""

from alembic import op


revision = "l2g3h4i5j6k7"
down_revision = "j0e1f2g3h4i5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_constraint("stock_instruments_isin_key", "stock_instruments", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "stock_instruments_isin_key",
        "stock_instruments",
        ["isin"],
    )
