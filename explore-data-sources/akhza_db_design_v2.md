# Bonds (اخزا) Database Design — v2

Bonds data splits into **reference/metadata** (PostgreSQL) and **time-series** (ClickHouse).
Column names are self-documenting — the collector layer maps TSETMC/SignalR field names to these clean names.

---

## Data Sources

| Source | Endpoint | Frequency | Data |
|--------|----------|-----------|------|
| TSETMC REST | `GetInstrumentSearch/{keyword}` | On discovery | Instrument list (active + expired) |
| TSETMC REST | `GetInstrumentInfo/{insCode}` | On discovery / daily | Instrument metadata |
| TSETMC REST | `BestLimits/{insCode}/{yyyymmdd}` | Every 1 s (poll) | Order-book snapshots (top-5 bid/ask) |
| TSETMC REST | `ClosingPrice/GetClosingPriceHistory/{insCode}` | Daily | Daily trade ticks (price, volume) |
| SignalR (ParsianBroker) | Real-time push | ~1 s | Live trade ticks + order-book updates |

---

## PostgreSQL — Reference Data

### `bond_instruments`

One row per bond instrument (active or expired).

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `instrument_code` | `VARCHAR(20) PK` | both | TSETMC 12–17 digit instrument code |
| `name_fa` | `VARCHAR(200)` | both | Persian name (e.g. اسنادخزانه-م2بودجه02-050923) |
| `name_en` | `VARCHAR(100)` | info | English name (e.g. TreasuryBill260615) |
| `symbol` | `VARCHAR(50)` | both | Trading symbol (e.g. اخزا201) |
| `isin` | `VARCHAR(30) UNIQUE` | info | ISIN code (e.g. IRB3TR160593) |
| `instrument_id` | `VARCHAR(50)` | info | Alternative instrument ID |
| `total_issued` | `BIGINT` | info | Total issued units |
| `base_volume` | `INT` | info | Base trade volume |
| `market_code` | `SMALLINT` | both | Market code (2 = Fara Bourse) |
| `market_name` | `VARCHAR(100)` | info | Market display name (e.g. بازار فرابورس) |
| `segment_code` | `VARCHAR(10)` | both | Market segment code (I1 = Novel Financial Instruments) |
| `segment_name` | `VARCHAR(100)` | info | Market segment display name |
| `security_type_code` | `VARCHAR(10)` | info | Security type code (69 = تامين مالي) |
| `security_type_name` | `VARCHAR(100)` | info | Security type display name |
| `price_ceiling` | `NUMERIC(18,2)` | info | Upper static price threshold |
| `price_floor` | `NUMERIC(18,2)` | info | Lower static price threshold |
| `low_52w` | `NUMERIC(18,2)` | info | 52-week low |
| `high_52w` | `NUMERIC(18,2)` | info | 52-week high |
| `low_yearly` | `NUMERIC(18,2)` | info | Yearly low |
| `high_yearly` | `NUMERIC(18,2)` | info | Yearly high |
| `avg_daily_volume_5y` | `BIGINT` | info | 5-year average daily trade volume |
| `last_trade_date` | `INT` | info | Last trade date (YYYYMMDD) |
| `status` | `VARCHAR(20)` | derived | `'active'` or `'expired'` — derived at upsert time |
| `maturity_date` | `DATE` | parsed | Maturity date parsed from `name_en` suffix (see below) |
| `listing_date` | `DATE` | collector | First observed trade date — set by collector on first tick |
| `created_at` | `TIMESTAMPTZ` | system | |
| `updated_at` | `TIMESTAMPTZ` | system | |

**Indexes:**
- PK: `instrument_code`
- Unique: `isin`
- Index: `symbol` (quick lookups by short code)
- Index: `status` (filter active vs expired)
- Index: `maturity_date` (filter by maturity range)

**Maturity Date Parser**

Parsed from the 6-digit suffix of `name_en`. Pattern: `TreasuryBill` + `YYMMDD` (Gregorian).

```python
import re, datetime

match = re.search(r'(\d{6})$', name_en)
if match:
    raw = match.group(1)
    maturity_date = datetime.date(2000 + int(raw[:2]), int(raw[2:4]), int(raw[4:6]))
```

**Upsert Pattern**

```sql
INSERT INTO bond_instruments (
    instrument_code, name_fa, name_en, symbol, isin,
    total_issued, base_volume, market_code, market_name,
    segment_code, segment_name, security_type_code, security_type_name,
    price_ceiling, price_floor, low_52w, high_52w,
    low_yearly, high_yearly, avg_daily_volume_5y, last_trade_date
)
VALUES (...)
ON CONFLICT (instrument_code) DO UPDATE SET
    name_fa               = EXCLUDED.name_fa,
    name_en               = EXCLUDED.name_en,
    symbol                = EXCLUDED.symbol,
    isin                  = EXCLUDED.isin,
    total_issued          = EXCLUDED.total_issued,
    base_volume           = EXCLUDED.base_volume,
    market_code           = EXCLUDED.market_code,
    market_name           = EXCLUDED.market_name,
    segment_code          = EXCLUDED.segment_code,
    segment_name          = EXCLUDED.segment_name,
    security_type_code    = EXCLUDED.security_type_code,
    security_type_name    = EXCLUDED.security_type_name,
    price_ceiling         = EXCLUDED.price_ceiling,
    price_floor           = EXCLUDED.price_floor,
    low_52w               = EXCLUDED.low_52w,
    high_52w              = EXCLUDED.high_52w,
    low_yearly            = EXCLUDED.low_yearly,
    high_yearly           = EXCLUDED.high_yearly,
    avg_daily_volume_5y   = EXCLUDED.avg_daily_volume_5y,
    last_trade_date       = EXCLUDED.last_trade_date,
    status                = CASE WHEN EXCLUDED.last_trade_date > 0 THEN 'active' ELSE 'expired' END,
    updated_at            = NOW();
```

---

## ClickHouse — Time-Series Data

### `bond_order_book`

Order-book snapshots — top-5 bid/ask levels. Captured every time the order book changes during a trading day.

| Column | Type | Notes |
|--------|------|-------|
| `instrument_code` | `String` | Instrument code |
| `trade_date` | `Date` | Trade date |
| `trade_time` | `UInt32` | Time (HHMMSS) |
| `ref_id` | `UInt64` | Reference ID from source |
| `depth_level` | `UInt8` | Order book depth (1 = best price, 5 = worst) |
| `bid_price` | `Float64` | Bid price (demand) |
| `bid_volume` | `UInt64` | Bid volume at this price level |
| `bid_order_count` | `UInt32` | Number of bid orders at this price level |
| `ask_price` | `Float64` | Ask price (offer) |
| `ask_volume` | `UInt64` | Ask volume at this price level |
| `ask_order_count` | `UInt32` | Number of ask orders at this price level |
| `data_source` | `LowCardinality(String)` | `'rest'` or `'signalr'` |
| `ingested_at` | `DateTime` | Ingestion timestamp (server time) |

**Engine:** `ReplicatedMergeTree`

**ORDER BY:** `(instrument_code, trade_date, trade_time, depth_level)`

**PARTITION BY:** `toYYYYMM(trade_date)`

**TTL:** 1 year

```sql
ALTER TABLE bond_order_book
    MODIFY TTL trade_date + INTERVAL 1 YEAR TO VOLUME 'cold_storage';
```

**Sample Queries**

```sql
-- Best bid/ask (level 1) over a day
SELECT instrument_code, trade_time, bid_price, bid_volume, ask_price, ask_volume
FROM bond_order_book
WHERE instrument_code = '21702706902357649'
  AND trade_date = '2026-06-08'
  AND depth_level = 1
ORDER BY trade_time ASC;

-- Daily spread statistics
SELECT instrument_code, trade_date,
       min(ask_price - bid_price) AS min_spread,
       max(ask_price - bid_price) AS max_spread,
       avg(ask_price - bid_price) AS avg_spread
FROM bond_order_book
WHERE depth_level = 1
  AND bid_price > 0 AND ask_price > 0
GROUP BY instrument_code, trade_date;

-- Full depth snapshot at a specific time
SELECT trade_time, depth_level,
       bid_price, bid_volume, bid_order_count,
       ask_price, ask_volume, ask_order_count
FROM bond_order_book
WHERE instrument_code = '21702706902357649'
  AND trade_date = '2026-06-08'
  AND trade_time BETWEEN 90000 AND 90100
ORDER BY trade_time, depth_level;
```

---

### `bond_trades`

Tick-level trade records — every executed trade with price and volume. This is the core analytical table for VWAP, OHLCV, and volume analysis.

| Column | Type | Notes |
|--------|------|-------|
| `instrument_code` | `String` | Instrument code |
| `trade_date` | `Date` | Trade date |
| `trade_time` | `UInt32` | Trade time (HHMMSS from REST, HHMMSSmmm from SignalR) |
| `trade_id` | `UInt64` | Unique trade ID from source. 0 when not provided (SignalR may omit). |
| `price` | `Float64` | Trade price (IRR) |
| `volume` | `UInt64` | Trade volume (number of bonds) |
| `value` | `Float64` | Trade value = `price * volume` — precomputed for aggregation speed |
| `is_canceled` | `UInt8` | 0 = normal trade, 1 = canceled / corrected |
| `data_source` | `LowCardinality(String)` | `'rest'` or `'signalr'` |
| `ingested_at` | `DateTime` | Ingestion timestamp (server time) |

**Engine:** `ReplicatedMergeTree`

**ORDER BY:** `(instrument_code, trade_date, trade_time, trade_id)`

**PARTITION BY:** `toYYYYMM(trade_date)`

**TTL:** 1 year

```sql
ALTER TABLE bond_trades
    MODIFY TTL trade_date + INTERVAL 1 YEAR TO VOLUME 'cold_storage';
```

**Design Decisions**

- **Why `trade_date` + `trade_time` instead of `DateTime64`?** Both TSETMC REST and SignalR deliver date/time as separate fields. Keeping them separate eliminates parsing ambiguity and matches native source formats.
- **Why `trade_id` in ORDER BY?** When REST and SignalR both report the same trade, the composite key `(instrument_code, trade_date, trade_time, trade_id)` ensures uniqueness without relying on ReplacingMergeTree (which silently discards data). Deduplication or conflict resolution happens at the application layer.
- **Why `value` precomputed?** While `price * volume` is cheap to compute per-row, precomputing it eliminates query-time CPU on VWAP and total-value aggregations across billions of rows.

**Sample Queries**

```sql
-- All trades for one instrument on one day
SELECT trade_time, price, volume, value, data_source
FROM bond_trades
WHERE instrument_code = '21702706902357649'
  AND trade_date = '2026-06-08'
ORDER BY trade_time ASC;

-- VWAP (Volume-Weighted Average Price)
SELECT instrument_code, trade_date,
       sum(value) / sum(volume) AS vwap,
       sum(volume) AS total_volume,
       sum(value) AS total_value,
       count() AS trade_count
FROM bond_trades
WHERE instrument_code = '21702706902357649'
  AND trade_date = '2026-06-08'
  AND is_canceled = 0
GROUP BY instrument_code, trade_date;

-- Intraday hourly OHLCV bars (computed on-the-fly, no separate OHLC table)
SELECT instrument_code, trade_date,
       toHour(trade_time) AS hour,
       argMin(price, trade_time) AS open,
       max(price) AS high,
       min(price) AS low,
       argMax(price, trade_time) AS close,
       sum(volume) AS volume,
       sum(value) / sum(volume) AS vwap
FROM bond_trades
WHERE instrument_code = '21702706902357649'
  AND trade_date = '2026-06-08'
  AND is_canceled = 0
GROUP BY instrument_code, trade_date, hour
ORDER BY hour ASC;

-- Latest 10 trades across all instruments
SELECT instrument_code, trade_date, trade_time, price, volume
FROM bond_trades
WHERE trade_date >= today() - 1
ORDER BY trade_date DESC, trade_time DESC
LIMIT 10;
```

---

## Complete Schema Summary

```
┌──────────────────────────────────────────────────────────┐
│                    PostgreSQL                            │
│                                                           │
│  bond_instruments                                         │
│  ├── instrument_code    VARCHAR(20)  PK                   │
│  ├── name_fa            VARCHAR(200)    Persian name      │
│  ├── name_en            VARCHAR(100)    English name      │
│  ├── symbol             VARCHAR(50)     Trading symbol    │
│  ├── isin               VARCHAR(30) UNIQUE                │
│  ├── total_issued       BIGINT                            │
│  ├── market_code        SMALLINT        2 = Fara Bourse   │
│  ├── market_name        VARCHAR(100)                      │
│  ├── segment_code       VARCHAR(10)     I1 = Novel FI     │
│  ├── segment_name       VARCHAR(100)                      │
│  ├── security_type_code VARCHAR(10)                       │
│  ├── security_type_name VARCHAR(100)                      │
│  ├── price_ceiling      NUMERIC(18,2)                     │
│  ├── price_floor        NUMERIC(18,2)                     │
│  ├── low_52w            NUMERIC(18,2)                     │
│  ├── high_52w           NUMERIC(18,2)                     │
│  ├── low_yearly         NUMERIC(18,2)                     │
│  ├── high_yearly        NUMERIC(18,2)                     │
│  ├── avg_daily_volume_5y BIGINT                           │
│  ├── last_trade_date    INT            YYYYMMDD           │
│  ├── status             VARCHAR(20)    active / expired   │
│  ├── maturity_date      DATE                              │
│  ├── listing_date       DATE                              │
│  ├── created_at         TIMESTAMPTZ                       │
│  └── updated_at         TIMESTAMPTZ                       │
│                                                           │
│  Rows: ~40 (19 active + 21 expired)                      │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                    ClickHouse                             │
│                                                           │
│  bond_order_book                                          │
│  ├── instrument_code    String                            │
│  ├── trade_date         Date                              │
│  ├── trade_time         UInt32         HHMMSS             │
│  ├── ref_id             UInt64                            │
│  ├── depth_level        UInt8          1 = best, 5 = worst│
│  ├── bid_price          Float64                           │
│  ├── bid_volume         UInt64                            │
│  ├── bid_order_count    UInt32                            │
│  ├── ask_price          Float64                           │
│  ├── ask_volume         UInt64                            │
│  ├── ask_order_count    UInt32                            │
│  ├── data_source        LC(String)     rest / signalr     │
│  └── ingested_at        DateTime                          │
│                                                           │
│  ORDER BY:  (instrument_code, trade_date,                │
│              trade_time, depth_level)                     │
│  PARTITION: toYYYYMM(trade_date)                          │
│  Engine:    ReplicatedMergeTree                           │
│  TTL:       1 year → cold_storage                         │
│                                                           │
│  ────────────────────────────────────────────────────    │
│                                                           │
│  bond_trades                                              │
│  ├── instrument_code    String                            │
│  ├── trade_date         Date                              │
│  ├── trade_time         UInt32         HHMMSS / HHMMSSmmm │
│  ├── trade_id           UInt64                            │
│  ├── price              Float64        IRR                │
│  ├── volume             UInt64                            │
│  ├── value              Float64        price * volume     │
│  ├── is_canceled        UInt8          0=normal, 1=cancel │
│  ├── data_source        LC(String)     rest / signalr     │
│  └── ingested_at        DateTime                          │
│                                                           │
│  ORDER BY:  (instrument_code, trade_date,                │
│              trade_time, trade_id)                        │
│  PARTITION: toYYYYMM(trade_date)                          │
│  Engine:    ReplicatedMergeTree                           │
│  TTL:       1 year → cold_storage                         │
└──────────────────────────────────────────────────────────┘
```

---

## Data Collection Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                     Collector (Python)                        │
│                                                               │
│  DISCOVERY (daily, on startup):                               │
│    1. GET /InstrumentSearch/اخزا → Upsert bond_instruments    │
│    2. For each active instrument:                             │
│       GET /InstrumentInfo/{code} → Upsert bond_instruments    │
│       Parse maturity_date from name_en                        │
│                                                               │
│  HISTORICAL BACKFILL (one-time):                              │
│    For each instrument, for each trading day since listing:   │
│      GET /BestLimits/{code}/{date} → Batch insert (CH)       │
│      GET /ClosingPrice/{code}     → Batch insert (CH)       │
│                                                               │
│  REAL-TIME (every 1 second):                                  │
│    ┌─────────────────┐   ┌──────────────────┐                 │
│    │ TSETMC Poller   │   │ SignalR Listener │                 │
│    │ (HTTP GET)      │   │ (ParsianBroker)  │                 │
│    └────────┬────────┘   └────────┬─────────┘                 │
│             │                     │                            │
│             ▼                     ▼                            │
│    ┌──────────────────────────────────────────┐               │
│    │           Redis Streams                   │               │
│    │  stream:bond_order_book                  │               │
│    │  stream:bond_trades                      │               │
│    └───────────────────┬──────────────────────┘               │
│                        ▼                                       │
│    ┌──────────────────────────────────────────┐               │
│    │        ClickHouse Writer (batch)          │               │
│    │   Reads streams, bulk-inserts every 1 s   │               │
│    │   Also writes latest tick to Redis cache  │               │
│    └──────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────┘
```

**Batch Insert Pattern**

```python
async def flush_batch(rows: list[dict], table: str):
    if not rows:
        return
    await ch_client.insert(table, rows, column_names=list(rows[0].keys()))
```

**Redis Cache Keys (latest tick per instrument)**

```
cache:bond_latest:{instrument_code}  →  {"price": 842190, "volume": 150, "trade_time": 121530, ...}
```

Enables FastAPI to serve latest prices with a single `GET`, avoiding ClickHouse queries for every frontend refresh.

---

## Data Retention

| Table | Retention | Rationale |
|-------|-----------|-----------|
| `bond_instruments` | Indefinite | ~40 rows, negligible storage cost |
| `bond_order_book` | 1 year (TTL) | Order-book detail beyond 1 year rarely needed for backtesting |
| `bond_trades` | 1 year (TTL) | Trade tick volume is high; 1 year covers most research use cases |

---

## API → Schema Field Mapping

For reference, the collector layer translates TSETMC API field names to our schema:

| TSETMC API Field | Schema Column | Table |
|-------------------|---------------|-------|
| `insCode` | `instrument_code` | all |
| `lVal30` | `name_fa` | `bond_instruments` |
| `lVal18` | `name_en` | `bond_instruments` |
| `lVal18AFC` | `symbol` | `bond_instruments` |
| `cIsin` | `isin` | `bond_instruments` |
| `zTitad` | `total_issued` | `bond_instruments` |
| `baseVol` | `base_volume` | `bond_instruments` |
| `flow` | `market_code` | `bond_instruments` |
| `flowTitle` | `market_name` | `bond_instruments` |
| `cgrValCot` | `segment_code` | `bond_instruments` |
| `cgrValCotTitle` | `segment_name` | `bond_instruments` |
| `cSecVal` | `security_type_code` | `bond_instruments` |
| `lSecVal` | `security_type_name` | `bond_instruments` |
| `psGelStaMax` | `price_ceiling` | `bond_instruments` |
| `psGelStaMin` | `price_floor` | `bond_instruments` |
| `minWeek` | `low_52w` | `bond_instruments` |
| `maxWeek` | `high_52w` | `bond_instruments` |
| `minYear` | `low_yearly` | `bond_instruments` |
| `maxYear` | `high_yearly` | `bond_instruments` |
| `qTotTran5JAvg` | `avg_daily_volume_5y` | `bond_instruments` |
| `dEven` | `trade_date` / `last_trade_date` | all |
| `hEven` | `trade_time` | `bond_order_book`, `bond_trades` |
| `number` | `depth_level` | `bond_order_book` |
| `pMeDem` | `bid_price` | `bond_order_book` |
| `qTitMeDem` | `bid_volume` | `bond_order_book` |
| `zOrdMeDem` | `bid_order_count` | `bond_order_book` |
| `pMeOf` | `ask_price` | `bond_order_book` |
| `qTitMeOf` | `ask_volume` | `bond_order_book` |
| `zOrdMeOf` | `ask_order_count` | `bond_order_book` |
| `refID` | `ref_id` | `bond_order_book` |

---

## What's Next

After Bonds schema is finalized:
1. **Crypto (ClickHouse)** — `crypto_trades`, `crypto_order_book` with `exchange`, `base_asset`, `quote_asset`
2. **Crypto (PostgreSQL)** — `crypto_symbols` reference table
3. **Iran Stocks (ClickHouse)** — `stock_trades`, `stock_order_book` (same shape as bond tables)
4. **Iran Stocks (PostgreSQL)** — `stock_instruments` (same shape as `bond_instruments`)
