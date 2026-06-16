"""fix bond_instruments: last_trade_date date, instrument_id unique

Revision ID: a1b2c3d4e5f6
Revises: 87a0a44e6940
Create Date: 2026-06-16 19:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "87a0a44e6940"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM bond_instruments "
        "WHERE ctid NOT IN ("
        "    SELECT min(ctid) FROM bond_instruments "
        "    WHERE instrument_id IS NOT NULL "
        "    GROUP BY instrument_id"
        ")"
    )

    op.create_unique_constraint("uq_bond_instrument_id", "bond_instruments", ["instrument_id"])

    op.alter_column(
        "bond_instruments",
        "last_trade_date",
        type_=sa.Date(),
        postgresql_using=(
            "CASE "
            "    WHEN last_trade_date BETWEEN 19000101 AND 21001231 "
            "    THEN to_date(last_trade_date::text, 'YYYYMMDD') "
            "    ELSE NULL "
            "END"
        ),
        existing_type=sa.Integer(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "bond_instruments",
        "last_trade_date",
        type_=sa.Integer(),
        postgresql_using=(
            "CASE "
            "    WHEN last_trade_date IS NOT NULL "
            "    THEN EXTRACT(YEAR FROM last_trade_date)::integer * 10000 "
            "         + EXTRACT(MONTH FROM last_trade_date)::integer * 100 "
            "         + EXTRACT(DAY FROM last_trade_date)::integer "
            "    ELSE NULL "
            "END"
        ),
        existing_type=sa.Date(),
        existing_nullable=True,
    )

    op.drop_constraint("uq_bond_instrument_id", "bond_instruments", type_="unique")