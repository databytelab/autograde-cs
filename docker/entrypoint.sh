#!/bin/sh
# Backend container entrypoint.
#
# Migrations run here rather than being left as a manual step. Without this
# a fresh volume produced a backend that started, reported healthy, and then
# failed every request with "no such table" until someone remembered to run
# `alembic upgrade head` by hand.
#
# `alembic upgrade head` is idempotent: on an already-migrated database it is
# a no-op, so this is safe on every restart.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 "$@"
