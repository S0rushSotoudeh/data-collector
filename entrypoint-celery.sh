#!/bin/sh
set -e

echo "Running PostgreSQL migrations..."
alembic upgrade head

echo "Running ClickHouse migrations..."
python manage.py clickhouse migrate

echo "Starting Celery..."
exec "$@"