# Akhza (اخزا) Database Design

Based on the TSETMC API exploration, Akhza data splits cleanly into **reference/metadata** (PostgreSQL) and **time-series** (ClickHouse).

---

## PostgreSQL — Reference Data

### `akhza_instruments`

One row per instrument (active or expired). Populated via `GetInstrumentSearch` and `GetInstrumentInfo`.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `ins_code` | `VARCHAR(20) PK` | both | 12–17 digit TSETMC instrument code |
| `lval30` | `VARCHAR(200)` | both | Persian full name |
| `lval18` | `VARCHAR(100)` | info | English short name (e.g. TreasuryBill260615) |
| `lval18_afc` | `VARCHAR(50)` | both | Short code (e.g. اخزا201) |
| `c_isin` | `VARCHAR(30)` | info | ISIN code |
| `instrument_id` | `VARCHAR(50)` | info | Alternative ID |
| `z_titad` | `BIGINT` | info | Total issued units |
| `base_vol` | `INT` | info | Base trade volume |
| `flow` | `SMALLINT` | both | Market flow (2 = Fara Bourse) |
| `flow_title` | `VARCHAR(100)` | info | Market flow title |
| `cgr_val_cot` | `VARCHAR(10)` | both | Market segment code (I1 = Novel Financial Instruments) |
| `cgr_val_cot_title` | `VARCHAR(100)` | info | Market segment title |
| `c_sec_val` | `VARCHAR(10)` | info | Security type code |
| `l_sec_val` | `VARCHAR(100)` | info | Security type title |
| `ps_gel_sta_max` | `NUMERIC(18,2)` | info | Upper static price threshold |
| `ps_gel_sta_min` | `NUMERIC(18,2)` | info | Lower static price threshold |
| `min_week` | `NUMERIC(18,2)` | info | 52-week low |
| `max_week` | `NUMERIC(18,2)` | info | 52-week high |
| `min_year` | `NUMERIC(18,2)` | info | Yearly low |
| `max_year` | `NUMERIC(18,2)` | info | Yearly high |
| `q_tot_tran_5j_avg` | `BIGINT` | info | 5-year average daily trade volume |
| `d_even` | `INT` | info | Last trade date (YYYYMMDD) |
| `last_date` | `SMALLINT` | search | 1 = active, 0 = expired |
| `created_at` | `TIMESTAMPTZ` | system | Row creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | system | Row last-updated timestamp |

**Indexes:**
- PK: `ins_code`
- Unique: `c_isin`
- Index: `lval18_afc` (short-code lookups)
- Index: `last_date` (filter active vs expired)

---

## ClickHouse — Time-Series Data

### `akhza_best_limits`

Historical order-book snapshots (top-5 bid/ask). Captured every time the order book changes during a trading day.

| Column | Type | Notes |
|--------|------|-------|
| `ins_code` | `String` | Instrument code |
| `d_even` | `Date` | Trade date |
| `h_even` | `UInt32` | Time (HHMMSS) |
| `ref_id` | `UInt64` | Reference ID |
| `number` | `UInt8` | Rank in order book (1–5) |
| `p_me_dem` | `Float64` | Bid price |
| `q_tit_me_dem` | `UInt64` | Bid quantity |
| `z_ord_me_dem` | `UInt32` | Number of bid orders |
| `p_me_of` | `Float64` | Ask price |
| `q_tit_me_of` | `UInt64` | Ask quantity |
| `z_ord_me_of` | `UInt32` | Number of ask orders |

**Engine:** `ReplicatedReplacingMergeTree` (or `ReplicatedMergeTree` if duplicates are acceptable)

**ORDER BY:** `(ins_code, d_even, h_even, number)`

**PARTITION BY:** `toYYYYMM(d_even)`

**Sample Query — best bid/ask at a point in time:**
```sql
SELECT ins_code, h_even, p_me_dem, q_tit_me_dem, p_me_of, q_tit_me_of
FROM akhza_best_limits
WHERE ins_code = '21702706902357649'
  AND d_even = '2026-06-08'
  AND number = 1
ORDER BY h_even ASC
```

**Sample Query — daily spread range:**
```sql
SELECT ins_code, d_even,
       min(p_me_of - p_me_dem) AS min_spread,
       max(p_me_of - p_me_dem) AS max_spread,
       avg(p_me_of - p_me_dem) AS avg_spread
FROM akhza_best_limits
WHERE number = 1
GROUP BY ins_code, d_even
```

---

## Data Collection Pipeline Design

```
┌─────────────────────────────────────────────────────┐
│                  Collector (Python)                  │
│                                                      │
│ 1. Fetch search results → upsert akhza_instruments   │
│ 2. For each active ins_code:                         │
│    a. Fetch InstrumentInfo → upsert metadata         │
│    b. For each trading day (today, yesterday):        │
│       - Fetch BestLimits → batch insert to CH        │
│       - (future) Fetch ClosingPrice → insert to CH   │
│                                                      │
│ InstrumentInfo & search results → PostgreSQL          │
│ BestLimits snapshots          → ClickHouse            │
└─────────────────────────────────────────────────────┘
```

### Upsert Strategy (PostgreSQL)

```sql
INSERT INTO akhza_instruments (ins_code, lval30, lval18, ...)
VALUES (...)
ON CONFLICT (ins_code) DO UPDATE SET
    lval30       = EXCLUDED.lval30,
    lval18       = EXCLUDED.lval18,
    ...
    updated_at   = NOW();
```

### Batch Insert (ClickHouse)

```python
# Collect all best-limit rows for one day across all instruments
# then bulk insert via ClickHouse native protocol:
INSERT INTO akhza_best_limits VALUES (...), (...), ...
```

---

## Data Retention

| Table | Retention | Rationale |
|-------|-----------|-----------|
| `akhza_instruments` | Indefinite | Metadata rarely changes; keep forever |
| `akhza_best_limits` | Indefinite (manage via TTL or partitions) | Historical order-book data for backtesting. After 2+ years, move to cheaper storage or apply TTL. |

ClickHouse TTL example:
```sql
ALTER TABLE akhza_best_limits
    MODIFY TTL d_even + INTERVAL 5 YEAR TO VOLUME 'cold_storage';
```