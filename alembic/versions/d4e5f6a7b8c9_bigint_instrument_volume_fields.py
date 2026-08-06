"""use bigint for instrument volume fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-09 12:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = ("bond_instruments", "option_instruments", "stock_instruments")
COLUMNS = ("total_issued", "base_volume", "avg_daily_volume_5y")


def upgrade() -> None:
    for table_name in TABLES:
        for column_name in COLUMNS:
            op.alter_column(
                table_name,
                column_name,
                type_=sa.BigInteger(),
                existing_type=sa.Integer(),
                existing_nullable=True,
            )


def downgrade() -> None:
    for table_name in TABLES:
        for column_name in COLUMNS:
            op.alter_column(
                table_name,
                column_name,
                type_=sa.Integer(),
                existing_type=sa.BigInteger(),
                existing_nullable=True,
            )
