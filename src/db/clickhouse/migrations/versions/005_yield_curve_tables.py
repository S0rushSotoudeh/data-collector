from src.db.clickhouse.schema import YIELD_CURVE_FITS_TABLE, YIELD_CURVE_BONDS_TABLE
from src.db.clickhouse.schema import _YIELD_CURVE_FITS_DDL, _YIELD_CURVE_BONDS_DDL


def upgrade(client):
    client.command(_YIELD_CURVE_FITS_DDL)
    client.command(_YIELD_CURVE_BONDS_DDL)


def downgrade(client):
    client.command(f"DROP TABLE IF EXISTS `{YIELD_CURVE_FITS_TABLE}`")
    client.command(f"DROP TABLE IF EXISTS `{YIELD_CURVE_BONDS_TABLE}`")
