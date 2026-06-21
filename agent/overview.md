# Overview

High-performance market data aggregation for algorithmic trading. Collects real-time data from three markets into a unified system.

## Markets

| Market | Frequency |
|--------|-----------|
| Iran Stock (TSETMC) — ~700 stocks | 1 s |
| Crypto (Binance, Nobitex, Wallex) | 1 ms |
| Bonds (اخزا, IFB) | 1 s |

## Architecture

```
Data Collection Layer
  TSETMC Scraper | SignalR (Parsian) | Crypto Fetcher | Bond Scraper
          \              |                  |              /
           \_____________|__________________|_____________/
                         |
                     Redis Streams (buffer)
                         |
            ┌────────────┴────────────┐
        ClickHouse (ts)          PostgreSQL (metadata)
            └────────────┬────────────┘
                         |
                    FastAPI (REST + WS)
                         |
               React + TradingView Charts
```

## Data Flow

1. COLLECT → Python fetchers pull all markets concurrently
2. BUFFER → Each tick → Redis Streams (per-market)
3. STORE → ClickHouse Writer batches from Streams → ClickHouse; metadata → PostgreSQL
4. CACHE → Latest tick/symbol → Redis
5. SERVE → FastAPI reads historical from ClickHouse, latest from Redis, pushes via WS (Redis Pub/Sub)
6. DISPLAY → React renders streaming charts, watchlists, order books, heatmaps

## Design Philosophy

- **Single-machine first** — everything in Docker Compose, no distributed complexity
- **ClickHouse for ts, PostgreSQL for metadata** — columnar OLAP + relational source of truth
- **Graceful degradation** — retries, backoff, partial data availability
- **Developer experience** — minimal config, good docs, strong communities
- **Prefix all shell commands with `rtk`** — saves 60-90% tokens. See `.kilo/rules/rtk-rules.md`.
