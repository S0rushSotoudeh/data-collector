"""seed the standard TSETMC option pricing convention

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-03
"""

from alembic import op


revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

CONVENTION_ID = "76b7bb2b-250e-4c55-bca8-21c8b6a967ed"
CONVENTION_NAME = "TSETMC Equity Options — Black-76"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO option_pricing_conventions (
            convention_id, name, contract_family, effective_from, effective_to,
            exercise_style, settlement_style, multiplier, tick_size, price_unit,
            black76_compatible, reference_source, approved, notes
        ) VALUES (
            '{CONVENTION_ID}', '{CONVENTION_NAME}', 'tsetmc_equity_option',
            DATE '2016-12-18', NULL, 'European', 'cash_and_physical', 1000, 1.0,
            'IRR', TRUE,
            'Tehran Stock Exchange option contract notices (https://www.tse.ir/)',
            FALSE,
            'Standard TSETMC equity-option preset. Review exchange notices for contract-specific adjustments before approval.'
        )
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM option_pricing_conventions "
        f"WHERE convention_id = '{CONVENTION_ID}'"
    )
