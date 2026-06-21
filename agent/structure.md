# Project Structure

```
C:\project\data_collector\
├── docker-compose.yml          # 4 services: api, redis, postgres, clickhouse
├── Dockerfile                  # Multi-stage python:3.13-slim
├── entrypoint.sh               # Migrations → uvicorn --reload
├── manage.py                   # CLI: shell, bond-sync, clickhouse mig
├── pyproject.toml              # Dependencies & metadata
├── alembic.ini                 # PG migrations config
├── alembic/
│   ├── env.py
│   └── versions/               # 2 migrations applied
├── src/
│   ├── main.py                 # FastAPI app
│   ├── admin/
│   │   ├── __init__.py         # View registration
│   │   ├── auth.py             # BasicAuth
│   │   ├── bond_views.py       # BondInstrumentAdmin (CRUD)
│   │   ├── clickhouse_views.py # BondOrderBookView + BondTradesView
│   │   ├── task_views.py       # CeleryTasksView
│   │   └── templates/          # admin_base.html, order_book_list.html, trades_list.html, admin_tasks.html
│   ├── collectors/
│   │   └── bond/
│   │       ├── models.py           # BondSearchItem, BondInstrumentInfo, BestLimitEntry
│   │       ├── tsetmc_client.py    # Async HTTP client (retry + semaphore)
│   │       ├── transformer.py      # API→DB mapping
│   │       ├── instrument_sync.py  # TSETMC→PG upsert
│   │       ├── order_book_fetcher.py # PG→TSETMC→CH backfill
│   │       └── run_sync.py         # CLI: sync + backfill 7 days
│   ├── db/
│   │   ├── config.py, session.py
│   │   ├── models/bond.py      # BondInstrument SQLModel
│   │   └── clickhouse/
│   │       ├── __init__.py     # Client (sync/async, retry)
│   │       ├── bond.py         # Facade
│   │       ├── schema.py       # DDL, ensure_tables, migration orchestration
│   │       ├── insert.py       # Batch insert
│   │       ├── query.py        # 7 query functions
│   │       └── migrations/
│   │           ├── manager.py  # Custom migration framework
│   │           └── versions/   # 001–004 migrations
│   └── tests/
│       ├── conftest.py
│       ├── test_clickhouse_*.py (client, migrations, schema, query)
│       ├── test_models.py, test_price_conversion.py
│       └── test_bond_*.py (models, transformer, tsetmc_client, instrument_sync, order_book_fetcher)
└── explore-data-sources/
    ├── akhza_history.md, akhza_history.py
    ├── akhza_db_design.md, akhza_db_design_v2.md
```