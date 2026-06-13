# Bonds (اخزا) Database Schema — Plan

## Goal

Produce the complete database map for Bond (اخزا) market data, building on the existing `explore-data sources/akhza_db_design.md`. The deliverable is a refined schema-markdown document saved to `explore-data-sources/akhza_db_design_v2.md`.

## Data Sources

| Source | Data | Storage |
|--------|------|---------|
| TSETMC REST (`GetInstrumentSearch`, `GetInstrumentInfo`) | Instrument metadata | PostgreSQL |
| TSETMC REST (`BestLimits/{insCode}/{date}`) | Historical order-book snapshots | ClickHouse |
| TSETMC REST (trade history endpoint — to be discovered) | Historical trade ticks | ClickHouse |
| SignalR (ParsianBroker) real-time push | Live trade ticks (price, volume) | ClickHouse |

## Schema Overview

### PostgreSQL — Reference Data

| Table | Rows | Purpose |
|-------|------|---------|
| `akhza_instruments` | ~40 (active + expired) | Instrument metadata — ISIN, names, thresholds, maturity hints |

### ClickHouse — Time-Series Data

| Table | Granularity | Purpose |
|-------|-------------|---------|
| `akhza_best_limits` | Per order-book change (intraday snapshots) | Top-5 bid/ask levels for spread and depth analysis |
| `akhza_trades` | Per trade (tick-level) | Price × volume of every executed trade |

## Plan Steps

### Step 1 — Review existing DB design

- Read `explore-data-sources/akhza_db_design.md` (already done).
- Identify gaps: missing trade-tick table, no SignalR schema, `akhza_instruments` missing a maturity-date column.

### Step 2 — Design refined PostgreSQL table

- Start from the existing `akhza_instruments` definition.
- Add `maturity_date` (DATE) — parsed from `lval18` English name (e.g. `TreasuryBill260615` → 2026-06-15).
- Add `listing_date` (DATE) — first observed trade date.
- Add `status` (VARCHAR(20)) — `'active'` / `'expired'` (derived from `last_date` field).
- Refine columns: rename unclear names to snake_case conventions.

### Step 3 — Design ClickHouse `akhza_best_limits` (refine existing)

- Keep existing design with minor refinements:
  - Partition by `toYYYYMM(d_even)` ✓
  - ORDER BY `(ins_code, d_even, h_even, number)` ✓
  - Add `data_source` (VARCHAR(10)) — `'rest'` / `'signalr'` to track provenance.

### Step 4 — Design ClickHouse `akhza_trades` (new)

Design the core trade-tick table accepting data from both REST and SignalR:

| Column | Type | Notes |
|--------|------|-------|
| `ins_code` | `String` | Instrument code |
| `d_even` | `Date` | Trade date |
| `h_even` | `UInt32` | Trade time (HHMMSSmmm, millisecond precision) |
| `price` | `Float64` | Trade price (IRR) |
| `volume` | `UInt64` | Trade volume (number of bonds) |
| `value` | `Float64` | `price * volume` — precomputed trade value |
| `trade_id` | `UInt64` | Unique trade identifier from source |
| `data_source` | `LowCardinality(String)` | `'rest'` or `'signalr'` |
| `ingested_at` | `DateTime` | Ingestion timestamp |

Engine: `ReplicatedMergeTree`  
ORDER BY: `(ins_code, d_even, h_even)`  
PARTITION BY: `toYYYYMM(d_even)`

### Step 5 — Write `akhza_db_design_v2.md`

Combine all tables into a single markdown file with:
- Column definitions, types, and notes
- Indexes, ORDER BY, and PARTITION BY for ClickHouse tables
- Sample queries
- Data retention notes
- Upsert / batch-insert guidance

---

## What is OUT of scope

- No code/models/migrations — schema design only.
- No Crypto or Stock tables — Bonds only.
- No Redis key design (cache layer is separate).
- No SignalR connection or protocol design.
