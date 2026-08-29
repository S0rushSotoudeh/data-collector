# Gold Market Database Design

Gold market data is partitioned into **reference/metadata** (PostgreSQL) and **high-frequency time-series** (ClickHouse).

---

## PostgreSQL — Reference Data

### `gold_instruments`

Stores metadata for all official Gold funds and instruments. Populated via IME official fund universe and TSETMC `GetInstrumentInfo`.

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| `instrument_code` | `VARCHAR(20) PK` | TSETMC | Primary identifier (InsCode) |
| `name_fa` | `VARCHAR(200)` | TSETMC / IME | Persian full name |
| `name_en` | `VARCHAR(100)` | TSETMC | English name |
| `symbol` | `VARCHAR(50)` | TSETMC | Ticker symbol (e.g. عیار, طلا, کهربا) |
| `isin` | `VARCHAR(30)` | TSETMC | ISIN code |
| `instrument_id` | `VARCHAR(50)` | TSETMC | Unique Instrument ID |
| `total_issued` | `BIGINT` | TSETMC | Total issued units |
| `base_volume` | `BIGINT` | TSETMC | Base trade volume |
| `market_code` | `INTEGER` | TSETMC | Market code flow |
| `market_name` | `VARCHAR(100)` | TSETMC | Market name |
| `segment_code` | `VARCHAR(10)` | TSETMC | Market segment code |
| `segment_name` | `VARCHAR(100)` | TSETMC | Market segment title |
| `security_type_code` | `VARCHAR(10)` | TSETMC | Security type identifier |
| `security_type_name` | `VARCHAR(100)` | TSETMC | Security type title |
| `price_ceiling` | `NUMERIC(18,2)` | TSETMC | Static price ceiling |
| `price_floor` | `NUMERIC(18,2)` | TSETMC | Static price floor |
| `low_52w` | `NUMERIC(18,2)` | TSETMC | 52-week low |
| `high_52w` | `NUMERIC(18,2)` | TSETMC | 52-week high |
| `low_yearly` | `NUMERIC(18,2)` | TSETMC | Yearly low |
| `high_yearly` | `NUMERIC(18,2)` | TSETMC | Yearly high |
| `avg_daily_volume_5y` | `BIGINT` | TSETMC | 5-year average daily volume |
| `last_trade_date` | `DATE` | TSETMC | Last recorded trade date |
| `status` | `VARCHAR(20)` | System | Active / Expired |
| `created_at` | `TIMESTAMPTZ` | System | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | System | Record last update timestamp |

---

## ClickHouse — High-Frequency Time-Series Data

### `gold_order_book`

Historical top-5 depth limit snapshots.

```sql
CREATE TABLE IF NOT EXISTS gold_order_book (
    instrument_code   String,
    trade_date        Date,
    trade_time        UInt32,
    ref_id            UInt64,
    depth_level       UInt8,
    bid_price         Int64,
    bid_volume        UInt64,
    bid_order_count   UInt32,
    ask_price         Int64,
    ask_volume        UInt64,
    ask_order_count   UInt32,
    data_source       LowCardinality(String),
    ingested_at       DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (instrument_code, trade_date, trade_time, depth_level)
PARTITION BY toYYYYMM(trade_date)
TTL ingested_at + INTERVAL 1 YEAR;
```

### `gold_trades`

Individual executed trade records with scaled integer prices.

```sql
CREATE TABLE IF NOT EXISTS gold_trades (
    instrument_code   String,
    trade_date        Date,
    trade_time        UInt32,
    trade_id          UInt64,
    price             Int64,
    volume            UInt64,
    value             Int64,
    is_canceled       UInt8 DEFAULT 0,
    data_source       LowCardinality(String),
    ingested_at       DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (instrument_code, trade_date, trade_time, trade_id)
PARTITION BY toYYYYMM(trade_date)
TTL ingested_at + INTERVAL 1 YEAR;
```
