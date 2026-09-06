"""Store the encrypted Parsian stream credential."""

from alembic import op
import sqlalchemy as sa

revision = "p5j6k7l8m9n0"
down_revision = "o4i5j6k7l8m9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "parsian_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_ciphertext", sa.Text(), nullable=False),
        sa.Column("token_fingerprint", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_parsian_credentials_singleton"),
    )


def downgrade():
    op.drop_table("parsian_credentials")
