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

## Big Picture Architecture

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
| **Collectors** | **Python 3.14** | Async I/O handles 700+ concurrent scrapes per second. Best ecosystem for web scraping (BeautifulSoup, lxml). |
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

## Data Flow (High Level)

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

## Design Philosophy

- **Single-machine first** — All services run on one machine via Docker Compose. No distributed complexity until needed.
- **ClickHouse for time-series, PostgreSQL for metadata** — ClickHouse's columnar engine handles all tick storage and analytical queries with high compression and sub-100ms aggregations. PostgreSQL serves as the source of truth for symbol metadata, user management, and configuration data.
- **Graceful degradation** — Market data scraping is inherently unreliable (rate limits, network issues, site changes). Every component handles transient failures with retries, backoff, and partial data availability.
- **Developer experience** — The stack prioritizes tools with minimal configuration, good documentation, and strong communities.