#!/bin/sh
set -eu
if [ "${APP_ENV:-development}" = "production" ]; then
  python scripts/validate_production_env.py --quiet
fi
if [ "${RUN_DB_MIGRATIONS:-true}" = "true" ]; then
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
fi
if [ "${SEED_DEMO:-false}" = "true" ]; then
  if [ "${APP_ENV:-development}" = "production" ]; then
    echo "SEED_DEMO is forbidden in production" >&2
    exit 1
  fi
  python scripts/seed_demo.py
fi
exec "$@"
