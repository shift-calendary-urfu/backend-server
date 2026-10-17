#!/bin/sh

set -e

echo "Применение миграций Alembic..."
uv run alembic upgrade head

echo "Запуск сервера Uvicorn..."
exec uv run --frozen --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000
