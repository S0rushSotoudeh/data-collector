"""create stock_instruments

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-05 17:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('stock_instruments',
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
        sa.Column('listing_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('instrument_code'),
        sa.UniqueConstraint('isin'),
        sa.UniqueConstraint('instrument_id'),
    )
    op.create_index('idx_stock_symbol', 'stock_instruments', ['symbol'], unique=False)
    op.create_index('idx_stock_status', 'stock_instruments', ['status'], unique=False)
    op.create_index('idx_stock_security_type', 'stock_instruments', ['security_type_code'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_stock_security_type', table_name='stock_instruments')
    op.drop_index('idx_stock_status', table_name='stock_instruments')
    op.drop_index('idx_stock_symbol', table_name='stock_instruments')
    op.drop_table('stock_instruments')
