"""create option_instruments

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-04 19:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('option_instruments',
        sa.Column('instrument_code', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('name_fa', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column('name_en', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('symbol', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column('isin', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True),
        sa.Column('instrument_id', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column('total_issued', sa.Integer(), nullable=True),
        sa.Column('base_volume', sa.Integer(), nullable=True),
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
        sa.Column('avg_daily_volume_5y', sa.Integer(), nullable=True),
        sa.Column('last_trade_date', sa.Date(), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column('listing_date', sa.Date(), nullable=True),
        sa.Column('option_type', sqlmodel.sql.sqltypes.AutoString(length=4), nullable=True),
        sa.Column('strike_price', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('underlying_symbol', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('instrument_code'),
        sa.UniqueConstraint('isin'),
        sa.UniqueConstraint('instrument_id'),
    )
    op.create_index('idx_option_symbol', 'option_instruments', ['symbol'], unique=False)
    op.create_index('idx_option_status', 'option_instruments', ['status'], unique=False)
    op.create_index('idx_option_expiry', 'option_instruments', ['expiry_date'], unique=False)
    op.create_index('idx_option_underlying', 'option_instruments', ['underlying_symbol'], unique=False)
    op.create_index('idx_option_type', 'option_instruments', ['option_type'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_option_type', table_name='option_instruments')
    op.drop_index('idx_option_underlying', table_name='option_instruments')
    op.drop_index('idx_option_expiry', table_name='option_instruments')
    op.drop_index('idx_option_status', table_name='option_instruments')
    op.drop_index('idx_option_symbol', table_name='option_instruments')
    op.drop_table('option_instruments')
