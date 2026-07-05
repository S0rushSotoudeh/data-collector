from clickhouse_connect.driver import Client

from src.db.clickhouse import _ensure_client
from src.db.clickhouse.migrations.manager import upgrade as _migrate_upgrade, downgrade as _migrate_downgrade, history as _migrate_history, pending as _migrate_pending, check as _migrate_check

ORDER_BOOK_TABLE = "bond_order_book"
TRADES_TABLE = "bond_trades"
YIELD_CURVE_FITS_TABLE = "yield_curve_fits"
YIELD_CURVE_BONDS_TABLE = "yield_curve_bonds"

OPTION_ORDER_BOOK_TABLE = "option_order_book"
OPTION_TRADES_TABLE = "option_trades"

_ORDER_BOOK_DDL = (
    f"CREATE TABLE IF NOT EXISTS `{ORDER_BOOK_TABLE}` ("
    f"    instrument_code   String,"
    f"    trade_date        Date,"
    f"    trade_time        UInt32,"
    f"    ref_id            UInt64,"
    f"    depth_level       UInt8,"
    f"    bid_price         Int64,"
    f"    bid_volume        UInt64,"
    f"    bid_order_count   UInt32,"
    f"    ask_price         Int64,"
    f"    ask_volume        UInt64,"
    f"    ask_order_count   UInt32,"
    f"    data_source       LowCardinality(String),"
    f"    ingested_at       DateTime DEFAULT now()"
    f")"
    f"ENGINE = ReplacingMergeTree(ingested_at) "
    f"ORDER BY (instrument_code, trade_date, trade_time, depth_level) "
    f"PARTITION BY toYYYYMM(trade_date) "
    f"TTL ingested_at + INTERVAL 1 YEAR"
)

_TRADES_DDL = (
    f"CREATE TABLE IF NOT EXISTS `{TRADES_TABLE}` ("
    f"    instrument_code   String,"
    f"    trade_date        Date,"
    f"    trade_time        UInt32,"
    f"    trade_id          UInt64,"
    f"    price             Int64,"
    f"    volume            UInt64,"
    f"    value             Int64,"
    f"    is_canceled       UInt8 DEFAULT 0,"
    f"    data_source       LowCardinality(String),"
    f"    ingested_at       DateTime DEFAULT now()"
    f")"
    f"ENGINE = ReplacingMergeTree(ingested_at) "
    f"ORDER BY (instrument_code, trade_date, trade_time, trade_id) "
    f"PARTITION BY toYYYYMM(trade_date) "
    f"TTL ingested_at + INTERVAL 1 YEAR"
)

_OPTION_ORDER_BOOK_DDL = (
    f"CREATE TABLE IF NOT EXISTS `{OPTION_ORDER_BOOK_TABLE}` ("
    f"    instrument_code   String,"
    f"    trade_date        Date,"
    f"    trade_time        UInt32,"
    f"    ref_id            UInt64,"
    f"    depth_level       UInt8,"
    f"    bid_price         Int64,"
    f"    bid_volume        UInt64,"
    f"    bid_order_count   UInt32,"
    f"    ask_price         Int64,"
    f"    ask_volume        UInt64,"
    f"    ask_order_count   UInt32,"
    f"    data_source       LowCardinality(String),"
    f"    ingested_at       DateTime DEFAULT now()"
    f")"
    f"ENGINE = ReplacingMergeTree(ingested_at) "
    f"ORDER BY (instrument_code, trade_date, trade_time, depth_level) "
    f"PARTITION BY toYYYYMM(trade_date) "
    f"TTL ingested_at + INTERVAL 1 YEAR"
)

_OPTION_TRADES_DDL = (
    f"CREATE TABLE IF NOT EXISTS `{OPTION_TRADES_TABLE}` ("
    f"    instrument_code   String,"
    f"    trade_date        Date,"
    f"    trade_time        UInt32,"
    f"    trade_id          UInt64,"
    f"    price             Int64,"
    f"    volume            UInt64,"
    f"    value             Int64,"
    f"    is_canceled       UInt8 DEFAULT 0,"
    f"    data_source       LowCardinality(String),"
    f"    ingested_at       DateTime DEFAULT now()"
    f")"
    f"ENGINE = ReplacingMergeTree(ingested_at) "
    f"ORDER BY (instrument_code, trade_date, trade_time, trade_id) "
    f"PARTITION BY toYYYYMM(trade_date) "
    f"TTL ingested_at + INTERVAL 1 YEAR"
)

ORDER_BOOK_COLUMNS = [
    "instrument_code",
    "trade_date",
    "trade_time",
    "ref_id",
    "depth_level",
    "bid_price",
    "bid_volume",
    "bid_order_count",
    "ask_price",
    "ask_volume",
    "ask_order_count",
    "data_source",
    "ingested_at",
]

TRADES_COLUMNS = [
    "instrument_code",
    "trade_date",
    "trade_time",
    "trade_id",
    "price",
    "volume",
    "value",
    "is_canceled",
    "data_source",
    "ingested_at",
]

OPTION_ORDER_BOOK_COLUMNS = [
    "instrument_code",
    "trade_date",
    "trade_time",
    "ref_id",
    "depth_level",
    "bid_price",
    "bid_volume",
    "bid_order_count",
    "ask_price",
    "ask_volume",
    "ask_order_count",
    "data_source",
    "ingested_at",
]

OPTION_TRADES_COLUMNS = [
    "instrument_code",
    "trade_date",
    "trade_time",
    "trade_id",
    "price",
    "volume",
    "value",
    "is_canceled",
    "data_source",
    "ingested_at",
]

YIELD_CURVE_FITS_COLUMNS = [
    "trade_date",
    "trade_time",
    "curve_side",
    "beta0",
    "beta1",
    "beta2",
    "lambda",
    "rmse",
    "n_bonds",
    "n_bonds_total",
    "converged",
    "error_message",
    "computed_at",
]

YIELD_CURVE_BONDS_COLUMNS = [
    "trade_date",
    "trade_time",
    "instrument_code",
    "curve_side",
    "symbol",
    "ttm_years",
    "price",
    "volume",
    "yield",
    "fitted_yield",
    "spread_bps",
    "computed_at",
]

_YIELD_CURVE_FITS_DDL = (
    f"CREATE TABLE IF NOT EXISTS `{YIELD_CURVE_FITS_TABLE}` ("
    f"    trade_date          Date,"
    f"    trade_time          UInt32,"
    f"    curve_side          LowCardinality(String),"
    f"    beta0               Nullable(Float64),"
    f"    beta1               Nullable(Float64),"
    f"    beta2               Nullable(Float64),"
    f"    lambda              Nullable(Float64),"
    f"    rmse                Nullable(Float64),"
    f"    n_bonds             UInt8,"
    f"    n_bonds_total       UInt8,"
    f"    converged           UInt8,"
    f"    error_message       String DEFAULT '',"
    f"    computed_at         DateTime64(3) DEFAULT now64(3)"
    f")"
    f"ENGINE = ReplacingMergeTree(computed_at) "
    f"ORDER BY (trade_date, trade_time, curve_side) "
    f"PARTITION BY toYYYYMM(trade_date)"
)

_YIELD_CURVE_BONDS_DDL = (
    f"CREATE TABLE IF NOT EXISTS `{YIELD_CURVE_BONDS_TABLE}` ("
    f"    trade_date          Date,"
    f"    trade_time          UInt32,"
    f"    instrument_code     String,"
    f"    curve_side          LowCardinality(String),"
    f"    symbol              String,"
    f"    ttm_years           Float64,"
    f"    price               Nullable(Int64),"
    f"    volume              Nullable(UInt64),"
    f"    yield               Nullable(Float64),"
    f"    fitted_yield        Nullable(Float64),"
    f"    spread_bps          Nullable(Float64),"
    f"    computed_at         DateTime64(3) DEFAULT now64(3)"
    f")"
    f"ENGINE = ReplacingMergeTree(computed_at) "
    f"ORDER BY (instrument_code, trade_date, trade_time, curve_side) "
    f"PARTITION BY toYYYYMM(trade_date)"
)


def ensure_tables(client: Client | None = None) -> None:
    c = _ensure_client(client)
    c.command(_ORDER_BOOK_DDL)
    c.command(_TRADES_DDL)
    c.command(_OPTION_ORDER_BOOK_DDL)
    c.command(_OPTION_TRADES_DDL)
    c.command(_YIELD_CURVE_FITS_DDL)
    c.command(_YIELD_CURVE_BONDS_DDL)


def run_migrations(client: Client | None = None) -> list[int]:
    return _migrate_upgrade(client)


def downgrade_migration(client: Client | None = None) -> int | None:
    return _migrate_downgrade(client)


def migration_history(client: Client | None = None) -> list[dict[str, object]]:
    return _migrate_history(client)


def migration_pending(client: Client | None = None) -> list[int]:
    return _migrate_pending(client)


def migration_check(client: Client | None = None) -> bool:
    return _migrate_check(client)