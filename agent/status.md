# Implementation Status

## Component Status

| Component | Status |
|-----------|--------|
| Docker Compose | ✅ 4 services: api, redis, postgres, clickhouse |
| PostgreSQL schema | ✅ bond_instruments via SQLModel + alembic (2 migrations) |
| ClickHouse schema | ✅ bond_order_book (5-level depth), bond_trades — ReplacingMergeTree (4 migrations) |
| ClickHouse queries | ✅ 7 functions: latest OB, history, trades, VWAP, OHLCV, spread, latest trades |
| Price conversion | ✅ Int64 (rials), price_to_storage/price_from_storage |
| FastAPI skeleton | ✅ GET /, GET /health, SessionMiddleware, admin panel |
| Admin Panel | ✅ SQLAdmin, 4 views, BasicAuth, /admin |
| Manage CLI | ✅ manage.py shell, bond-sync, clickhouse migrate/downgrade/history/pending/check |
| Celery Tasks | ✅ 3 tasks: sync_bond_instruments, fetch_yesterday_orderbook, backfill_order_books_task |
| TSETMC Bond Scraper | ✅ async client, instrument sync, OB backfill |
| TSETMC Stock Scraper | ❌ |
| SignalR Listener | ❌ (empty placeholders) |
| Crypto Fetcher | ❌ |
| Redis Streams | ❌ (service running, no code) |
| Redis Cache | ❌ |
| ClickHouse Writer | ✅ (direct inserts via order_book_fetcher.py) |
| FastAPI REST endpoints | ❌ (query functions exist, no routes) |
| FastAPI WebSocket | ❌ |
| React Frontend | ❌ |
| Prometheus + Grafana | ❌ |

## Current State

Database layer is most complete. Database layer is most complete — CH migrations, PG schema, query functions tested. Admin panel provides CRUD for bond instruments + read-only CH views. Collectors, Redis pipeline, API endpoints, frontend not yet built.

## PostgreSQL Schema (bond_instruments)

PK: instrument_code (VARCHAR(20)). Unique: isin, instrument_id. Indexes: idx_bond_symbol, idx_bond_status, idx_bond_maturity.

Columns: instrument_code, name_fa, name_en, symbol, isin, instrument_id, total_issued, base_volume, market_code, market_name, segment_code, segment_name, security_type_code, security_type_name, price_ceiling, price_floor, low_52w, high_52w, low_yearly, high_yearly, avg_daily_volume_5y, last_trade_date, status, maturity_date, listing_date, created_at, updated_at

## ClickHouse Tables

**bond_order_book** — 5-level depth
- ORDER BY: (instrument_code, trade_date, trade_time, depth_level)
- PARTITION BY: toYYYYMM(trade_date)
- TTL: ingested_at + INTERVAL 1 YEAR
- Engine: ReplacingMergeTree(ingested_at)
- Columns: instrument_code, trade_date, trade_time, ref_id, depth_level, bid_price (Int64), bid_volume, bid_order_count, ask_price (Int64), ask_volume, ask_order_count, data_source, ingested_at

**bond_trades** — tick-level trades
- ORDER BY: (instrument_code, trade_date, trade_time, trade_id)
- PARTITION BY: toYYYYMM(trade_date)
- TTL: ingested_at + INTERVAL 1 YEAR
- Engine: ReplacingMergeTree(ingested_at)
- Columns: instrument_code, trade_date, trade_time, trade_id, price (Int64), volume, value, is_canceled, data_source, ingested_at

Prices stored as Int64 (integer rials) — convert via price_to_storage() / price_from_storage().