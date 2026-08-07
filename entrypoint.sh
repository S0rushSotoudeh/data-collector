#!/bin/sh
set -e

echo "Running PostgreSQL migrations..."
alembic upgrade head

echo "Running ClickHouse migrations..."
python manage.py clickhouse migrate

echo "Importing legacy operation runs..."
python manage.py import-legacy-runs

echo "Starting application..."
reload_arg=""
if [ "${APP_RELOAD}" = "true" ]; then
    reload_arg="--reload"
fi
exec uvicorn src.main:app --host "${APP_HOST}" --port "${APP_PORT}" ${reload_arg}
