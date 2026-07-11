"""add option underlying instrument code

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "option_instruments",
        sa.Column("underlying_instrument_code", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "idx_option_underlying_code",
        "option_instruments",
        ["underlying_instrument_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_option_underlying_code", table_name="option_instruments")
    op.drop_column("option_instruments", "underlying_instrument_code")
