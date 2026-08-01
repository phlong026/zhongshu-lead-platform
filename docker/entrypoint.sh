#!/bin/sh
set -eu
attempt=0
until alembic upgrade head; do
  attempt=$((attempt+1))
  if [ "$attempt" -ge 20 ]; then
    echo "database migration failed after $attempt attempts" >&2
    exit 1
  fi
  echo "database not ready, retrying ($attempt/20)..." >&2
  sleep 3
done
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python scripts/seed_demo.py
fi
exec "$@"
