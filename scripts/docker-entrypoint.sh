#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
python /app/scripts/wait_for_db.py

if [ "${SEED_ON_START:-true}" = "true" ]; then
  echo "Running database seed (idempotent)..."
  python -m scripts.seed
fi

echo "Starting API: $*"
exec "$@"
