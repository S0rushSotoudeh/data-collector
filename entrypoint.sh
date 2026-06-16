#!/bin/sh
set -e

echo "Running PostgreSQL migrations..."
alembic upgrade head

echo "Running ClickHouse migrations..."
python manage.py clickhouse migrate

echo "Starting application..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload