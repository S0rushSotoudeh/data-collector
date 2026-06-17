# Data Collector for HFT Analytics

## Project Idea

A high-performance market data collection and analytics platform that aggregates real-time data from **three distinct markets** into a unified system for algorithmic trading research and dashboard visualization.

### Markets Covered

| Market | Description | Update Frequency |
|--------|-------------|-----------------|
| **Iran Stock Market** | Tehran Stock Exchange — ~700 stocks (فولاد, فملی, وغیره). Collects via TSETMC HTTP scraping and SignalR (ParsianBroker) real-time feed. | Every 1 s |
| **Cryptocurrency** | Binance, Nobitex, Wallex — top pairs (BTC/USDT, ETH/USDT, etc.) | Every 1 ms |
| **Bonds (اخزا)** | Iranian Islamic Treasury Bonds — traded on IFB. Collects via TSETMC HTTP scraping and SignalR (ParsianBroker) real-time feed. | Every 1 s |

The goal is to collect tick-level data (price, volume, bid/ask) simultaneously from all sources, store it for fast retrieval, and serve it through a frontend dashboard for real-time monitoring and historical analysis.

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA COLLECTION LAYER                        │
│                                                                     │
│  ┌─────────────────┐   ┌──────────────────┐   ┌────────────────┐   ┌──────────────────┐  │
│  │ TSETMC Scraper  │   │ SignalR (Parsian)│   │ Crypto Fetcher │   │ Bond Scraper     │  │
│  │ (Iran Stocks)   │   │ (Iran Stocks/   │   │ (Binance etc.) │   │ (اخزا / IFB)     │  │
│  │                 │   │  Bonds)         │   │                │   │                  │  │
│  └────────┬────────┘   └────────┬─────────┘   └────────┬───────┘   └────────┬─────────┘  │
│           │                     │                       │                    │            │
│           └─────────────────────┼───────────────────────┼────────────────────┘            │
│                                 │                       │                                 │
│                                 └───────────┬───────────┘                                 │
│                                             ▼                                             │
│                                  ┌─────────────────────┐                                  │
│                                  │   Redis Streams     │  ← Message Queue Buffer          │
│                                  └──────────┬──────────┘                                  │
└────────────────────────┼───────────────────────────────────────────┘
                         │
┌────────────────────────┼───────────────────────────────────────────┐
│                STORAGE LAYER                   ▼                    │
│  ┌──────────────────────────┐  ┌───────────────────────────────┐   │
│  │        ClickHouse        │  │         PostgreSQL            │   │
│  │   All time-series data   │  │  Symbol metadata, user mgmt, │   │
│  │   (ticks, aggregates).   │  │  reference & config data.    │   │
│  │   Columnar OLAP engine.  │  │                               │   │
│  └──────────────────────────┘  └───────────────────────────────┘   │
└────────────────────────┼───────────────────────────────────────────┘
                         │
┌────────────────────────┼───────────────────────────────────────────┐
│              API LAYER                       ▼                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              FastAPI (REST + WebSocket)                   │      │
│  │   REST endpoints for historical queries.                 │      │
│  │   WebSocket for real-time streaming to frontend.         │      │
│  └──────────────────────┬───────────────────────────────────┘      │
└─────────────────────────┼──────────────────────────────────────────┘
                          │
┌─────────────────────────┼──────────────────────────────────────────┐
│              FRONTEND                           ▼                  │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │  React + TypeScript + Vite + TradingView Lightweight Charts│   │
│  │  Real-time price charts, watchlist, market depth,          │   │
│  │  sector heatmaps,                                          │   │
│  └────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Collectors** | **Python 3.13** | Async I/O handles 700+ concurrent scrapes per second. Best ecosystem for web scraping (BeautifulSoup, lxml). |
| **Message Queue** | **Redis Streams** | Ultra-low latency, no extra infrastructure (Redis is already needed for caching). |
| **Cache / Pub-Sub** | **Redis** | Caches latest tick per symbol for instant API responses. Pub/Sub pushes real-time updates to WebSocket clients. |
| **Time-Series Storage** | **ClickHouse** | Columnar OLAP database for all time-series data. 5-10× compression, sub-100ms aggregation queries on billions of rows. |
| **Reference Data** | **PostgreSQL** | Symbol metadata, user management, configuration, and reference data. No time-series extension needed. |
| **API Server** | **FastAPI** | Async Python framework. Native WebSocket support. Auto-generated OpenAPI docs. |
| **Frontend** | **React 18 + Vite + TypeScript** | Modern, fast dev experience. TypeScript for type safety. |
| **Charts** | **TradingView Lightweight Charts** | High-performance financial charts optimized for large datasets. |
| **Orchestration** | **Docker Compose** | Single `docker compose up` runs the entire stack locally. |
| **Monitoring** | **Prometheus + Grafana** | Collector health, data freshness, API latency dashboards. |

---

## Implementation Status

| Component | Status | Files / Details |
|-----------|--------|----------------|
| **Docker Compose** | ✅ Done | 4 services: `api` (FastAPI), `redis`, `postgres`, `clickhouse` |
| **PostgreSQL schema** | ✅ Done | `bond_instruments` table via SQLModel + alembic (2 migrations applied) |
| **ClickHouse schema** | ✅ Done | `bond_order_book` (5-level depth), `bond_trades` via custom migration system (3 versions) |
| **ClickHouse queries** | ✅ Done | 7 query functions: latest order book, history, trades, VWAP, OHLCV, spread, latest trades |
| **Price conversion** | ✅ Done | Int64 storage (rials) with `price_to_storage`/`price_from_storage` |
| **FastAPI skeleton** | ✅ Done | `GET /`, `GET /health`, SessionMiddleware, admin panel wired in |
| **Admin Panel** | ✅ Done | SQLAdmin with `sqladmin[full]>=0.27`. 3 views: `BondInstrumentAdmin` (CRUD), `BondOrderBookView` (query by code+date, latest snapshots), `BondTradesView` (query by code+date, latest trades). BasicAuth via `ADMIN_USER`/`ADMIN_PASSWORD`. Bound to `/admin`. |
| **Manage CLI** | ✅ Done | `manage.py shell`, `manage.py clickhouse {migrate,downgrade,history,pending,check}` |
| **TSETMC Bond Scraper** | ⚠️ Prototype | `explore-data-sources/akhza_history.py` — fetches instrument info & best limits from TSETMC |
| **TSETMC Stock Scraper** | ❌ Missing | — |
| **SignalR Listener** | ❌ Missing | Placeholder files exist (empty) |
| **Crypto Fetcher** | ❌ Missing | — |
| **Redis Streams** | ❌ Missing | Redis service running, no code writes/reads streams |
| **Redis Cache** | ❌ Missing | — |
| **ClickHouse Writer** | ❌ Missing | Insert functions exist (`insert.py`) but no consumer loop |
| **FastAPI REST endpoints** | ❌ Missing | Query functions exist in `src/db/clickhouse/query.py` but no routes wire them up |
| **FastAPI WebSocket** | ❌ Missing | — |
| **React Frontend** | ❌ Missing | — |
| **Prometheus + Grafana** | ❌ Missing | — |

---

## Project Structure

```
C:\project\data_collector\
├── docker-compose.yml          # 4 services: api, redis, postgres, clickhouse
├── Dockerfile                  # Multi-stage python:3.13-slim build
├── entrypoint.sh               # Runs migrations then uvicorn --reload
├── manage.py                   # CLI for shell & ClickHouse migrations
├── pyproject.toml              # Project metadata & dependencies
├── alembic.ini                 # Alembic config (PostgreSQL migrations)
├── alembic/
│   ├── env.py
│   └── versions/               # 2 migrations: initial + fix last_trade_date
├── src/
│   ├── main.py                 # FastAPI app (admin panel wired in)
│   ├── admin/
│   │   ├── __init__.py         # SQLAdmin setup, 3 views registered
│   │   ├── auth.py             # BasicAuthBackend (ADMIN_USER/ADMIN_PASSWORD)
│   │   ├── bond_views.py       # BondInstrumentAdmin (CRUD ModelView)
│   │   └── clickhouse_views.py # BondOrderBookView + BondTradesView (custom BaseView)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── config.py           # get_database_url() for PostgreSQL
│   │   ├── session.py          # SQLAlchemy engine + SessionLocal
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── bond.py         # BondInstrument SQLModel (30+ columns)
│   │   └── clickhouse/
│   │       ├── __init__.py     # Client connection (sync/async, retry)
│   │       ├── bond.py         # Facade re-exporting schema/insert/query
│   │       ├── schema.py       # Table DDL, ensure_tables, migration orchestration
│   │       ├── insert.py       # batch insert for order_book & trades
│   │       ├── query.py        # 7 query functions (latest, history, VWAP, OHLCV, etc.)
│   │       └── migrations/
│   │           ├── manager.py  # Custom migration framework (version discovery, apply, downgrade)
│   │           └── versions/
│   │               ├── 001_create_schema_migrations.py
│   │               ├── 002_create_bond_order_book.py
│   │               └── 003_create_bond_trades.py
│   └── tests/
│       ├── conftest.py
│       ├── test_clickhouse_client.py
│       ├── test_clickhouse_migrations.py
│       ├── test_clickhouse_schema.py
│       ├── test_clickhouse_query.py
│       ├── test_models.py
│       └── test_price_conversion.py
└── explore-data-sources/
    ├── akhza_history.md        # TSETMC API research notes
    ├── akhza_history.py        # Working TSETMC bond data fetcher prototype
    ├── akhza_db_design.md      # v1 DB design
    ├── akhza_db_design_v2.md   # v2 DB design (clean column names)
    ├── tesetmc.py              # Placeholder (empty)
    └── signalr.py              # Placeholder (empty)
```

---

## Data Flow (Target)

```
Every 1 second:

1. COLLECT → Python collectors fetch price/volume/bid/ask from all markets
              (TSETMC via HTTP scraping, SignalR via ParsianBroker real-time push,
               crypto via WebSocket/REST)

2. BUFFER  → Each tick is published to Redis Streams
              (separate streams for stock / crypto / bond)

3. STORE   → ClickHouse Writer reads from Redis Streams in batches
              and bulk-inserts ticks into ClickHouse (all time-series data).
              PostgreSQL stores symbol metadata, user info, and reference data.

4. CACHE   → Latest tick per symbol written to Redis
              (for instant frontend access)

5. SERVE   → FastAPI reads historical data from ClickHouse
              Latest prices from Redis
              Pushes real-time updates via WebSocket (powered by Redis Pub/Sub)

6. DISPLAY → React frontend renders streaming charts, watchlists,
              order books, and sector heatmaps
```

---

## Current State

The **database layer** is the most complete part. ClickHouse migrations, PostgreSQL schema, and all analytical query functions are implemented and tested. The **admin panel** (SQLAdmin) provides CRUD for bond instruments and read-only views for ClickHouse data. The surface area (collectors, Redis pipeline, API endpoints, frontend) is not yet built.

### PostgreSQL Schema (`bond_instruments`)

- **PK:** `instrument_code` (VARCHAR(20))
- **Unique:** `isin`, `instrument_id`
- **Indexes:** `idx_bond_symbol`, `idx_bond_status`, `idx_bond_maturity`
- Columns: instrument_code, name_fa, name_en, symbol, isin, instrument_id, total_issued, base_volume, market_code, market_name, segment_code, segment_name, security_type_code, security_type_name, price_ceiling, price_floor, low_52w, high_52w, low_yearly, high_yearly, avg_daily_volume_5y, last_trade_date, status, maturity_date, listing_date, created_at, updated_at

### ClickHouse Tables

**`bond_order_book`** — 5-level depth snapshots
- ORDER BY: `(instrument_code, trade_date, trade_time, depth_level)`
- PARTITION BY: `toYYYYMM(trade_date)`
- TTL: `ingested_at + INTERVAL 1 YEAR`
- Engine: MergeTree
- Columns: instrument_code, trade_date, trade_time, ref_id, depth_level, bid_price (Int64), bid_volume, bid_order_count, ask_price (Int64), ask_volume, ask_order_count, data_source, ingested_at

**`bond_trades`** — Tick-level trade records
- ORDER BY: `(instrument_code, trade_date, trade_time, trade_id)`
- PARTITION BY: `toYYYYMM(trade_date)`
- TTL: `ingested_at + INTERVAL 1 YEAR`
- Engine: MergeTree
- Columns: instrument_code, trade_date, trade_time, trade_id, price (Int64), volume, value, is_canceled, data_source, ingested_at

Prices stored as **Int64** (integer rials) — converted via `price_to_storage()` / `price_from_storage()`.

---

## Design Philosophy

- **Single-machine first** — All services run on one machine via Docker Compose. No distributed complexity until needed.
- **ClickHouse for time-series, PostgreSQL for metadata** — ClickHouse's columnar engine handles all tick storage and analytical queries with high compression and sub-100ms aggregations. PostgreSQL serves as the source of truth for symbol metadata, user management, and configuration data.
- **Graceful degradation** — Market data scraping is inherently unreliable (rate limits, network issues, site changes). Every component handles transient failures with retries, backoff, and partial data availability.
- **Developer experience** — The stack prioritizes tools with minimal configuration, good documentation, and strong communities.

---

## Development Workflow

All code is developed and tested inside Docker Compose — do not run Python directly on the host.

### Hot Reload

The `api` service uses `uvicorn --reload` and mounts `./src:/app/src` as a volume. Any change to Python files in `src/` triggers an automatic server restart inside the container.

### Running Tests

```bash
# Run all tests in the api container
docker compose exec api python -m pytest

# With coverage
docker compose exec api python -m pytest --cov=src

# Run a specific test file
docker compose exec api python -m pytest src/tests/test_clickhouse_query.py
```

### Running Code

```bash
# Start all services (build first)
docker compose up --build

# Rebuild and start in detached mode
docker compose up --build -d

# View logs for a specific service
docker compose logs -f api

# Restart a service (automatic with --reload, but can force)
docker compose restart api

# Open a shell inside the api container
docker compose exec api bash

# Interactive Python shell with project imports
docker compose exec api python manage.py shell
```

### Managing Dependencies

```bash
# Add a dependency
docker compose exec api uv add some-package

# Remove a dependency
docker compose exec api uv remove some-package

# Sync lockfile after manual pyproject.toml changes
docker compose exec api uv sync
```

### ClickHouse Migrations

Custom migration framework (not alembic — that's only for PostgreSQL):

```bash
# Apply pending migrations
docker compose exec api python manage.py clickhouse migrate

# Revert last migration
docker compose exec api python manage.py clickhouse downgrade

# Show applied migrations
docker compose exec api python manage.py clickhouse history

# List pending migrations
docker compose exec api python manage.py clickhouse pending

# Exit non-zero if pending migrations exist
docker compose exec api python manage.py clickhouse check
```

### PostgreSQL Migrations

Uses standard alembic (runs automatically on container startup via `entrypoint.sh`):

```bash
# Create a new migration
docker compose exec api alembic revision --autogenerate -m "description"

# Run pending (automatic on startup, but can run manually)
docker compose exec api alembic upgrade head
```

### Linting & Type Checking

```bash
docker compose exec api ruff check src/
docker compose exec api mypy src/
```