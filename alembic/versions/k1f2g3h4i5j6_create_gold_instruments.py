"""create gold_instruments

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2026-08-30 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "k1f2g3h4i5j6"
down_revision: Union[str, None] = "j0e1f2g3h4i5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'gold_instruments',
        sa.Column('instrument_code', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('name_fa', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column('name_en', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('symbol', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column('isin', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True),
        sa.Column('instrument_id', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column('total_issued', sa.BigInteger(), nullable=True),
        sa.Column('base_volume', sa.BigInteger(), nullable=True),
        sa.Column('market_code', sa.Integer(), nullable=True),
        sa.Column('market_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('segment_code', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.Column('segment_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('security_type_code', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.Column('security_type_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('price_ceiling', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('price_floor', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('low_52w', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('high_52w', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('low_yearly', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('high_yearly', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('avg_daily_volume_5y', sa.BigInteger(), nullable=True),
        sa.Column('last_trade_date', sa.Date(), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column('maturity_date', sa.Date(), nullable=True),
        sa.Column('listing_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('instrument_code'),
    )
    op.create_index('idx_gold_symbol', 'gold_instruments', ['symbol'], unique=False)
    op.create_index('idx_gold_status', 'gold_instruments', ['status'], unique=False)
    op.create_index('idx_gold_maturity', 'gold_instruments', ['maturity_date'], unique=False)
    op.create_index('idx_gold_isin', 'gold_instruments', ['isin'], unique=False)
    op.create_index('idx_gold_instrument_id', 'gold_instruments', ['instrument_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_gold_instrument_id', table_name='gold_instruments')
    op.drop_index('idx_gold_isin', table_name='gold_instruments')
    op.drop_index('idx_gold_maturity', table_name='gold_instruments')
    op.drop_index('idx_gold_status', table_name='gold_instruments')
    op.drop_index('idx_gold_symbol', table_name='gold_instruments')
    op.drop_table('gold_instruments')
