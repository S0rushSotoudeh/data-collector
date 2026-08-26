"""add IME physical-market metadata

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "i9d0e1f2g3h4"
down_revision = "h8c9d0e1f2g3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ime_producers",
        sa.Column("producer_code", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("producer_code"),
    )
    op.create_index("ix_ime_producers_name", "ime_producers", ["name"])
    op.create_index("ix_ime_producers_enabled", "ime_producers", ["enabled"])
    op.create_table(
        "ime_products",
        sa.Column("producer_code", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(120), nullable=False),
        sa.Column("goods_name", sa.String(500), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False, server_default=""),
        sa.Column("currency", sa.String(40), nullable=False, server_default=""),
        sa.Column("category", sa.String(80), nullable=True),
        sa.Column("last_trade_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["producer_code"], ["ime_producers.producer_code"]),
        sa.PrimaryKeyConstraint("producer_code", "symbol"),
        sa.UniqueConstraint("producer_code", "symbol", name="uq_ime_product_producer_symbol"),
    )
    op.create_index("ix_ime_products_last_trade_date", "ime_products", ["last_trade_date"])
    op.create_index("idx_ime_products_producer_name", "ime_products", ["producer_code", "goods_name"])
    op.execute(
        "INSERT INTO ime_producers (producer_code, name, enabled) "
        "VALUES (5219, 'سیمان مازندران', true) ON CONFLICT (producer_code) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("ime_products")
    op.drop_table("ime_producers")
