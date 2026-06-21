# Dev Workflow

All code runs inside Docker Compose — never run Python directly on host.

## Hot Reload

`api` service uses `uvicorn --reload`, mounts `./src:/app/src`. File changes auto-restart.

## Running Tests

```bash
docker compose exec api python -m pytest
docker compose exec api python -m pytest --cov=src
docker compose exec api python -m pytest src/tests/test_clickhouse_query.py
```

## Docker Commands

```bash
docker compose up --build           # Start all services
docker compose up --build -d        # Rebuild + detach
docker compose logs -f api          # Tail logs
docker compose restart api          # Force restart
docker compose exec api bash        # Shell in container
docker compose exec api python manage.py shell   # Python shell
```

## Dependencies

```bash
docker compose exec api uv add some-package
docker compose exec api uv remove some-package
docker compose exec api uv sync
```

## ClickHouse Migrations (custom framework)

```bash
docker compose exec api python manage.py clickhouse migrate
docker compose exec api python manage.py clickhouse downgrade
docker compose exec api python manage.py clickhouse history
docker compose exec api python manage.py clickhouse pending
docker compose exec api python manage.py clickhouse check
```

## PostgreSQL Migrations (alembic)

Auto-runs on startup via entrypoint.sh.

```bash
docker compose exec api alembic revision --autogenerate -m "description"
docker compose exec api alembic upgrade head
```

## Linting

```bash
python -c "import py_compile; py_compile.compile(...)"
```

Full linting only if pyproject.toml lists the tool as a dependency.