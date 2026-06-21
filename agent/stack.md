# Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Collectors | Python 3.13 | Async I/O, best scraping ecosystem |
| Message Queue | Redis Streams | Ultra-low latency, no extra infra |
| Cache / Pub-Sub | Redis | Latest tick cache, WS push via Pub/Sub |
| Time-Series Storage | ClickHouse | Columnar OLAP, 5-10x compression, sub-100ms aggregations |
| Reference Data | PostgreSQL | Metadata, users, config |
| API Server | FastAPI | Async, native WS, auto OpenAPI |
| Frontend | React 18 + Vite + TypeScript | Modern, fast dev, type safety |
| Charts | TradingView Lightweight Charts | High-performance financial charts |
| Orchestration | Docker Compose | Single `docker compose up` |
| Monitoring | Prometheus + Grafana | Collector health, data freshness, latency |