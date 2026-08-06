#!/bin/sh
set -eu
. /app/docker/prepare-env.sh
if [ "${APP_ENV:-development}" = "production" ]; then
  python scripts/validate_production_env.py --quiet
fi
exec python scripts/scheduler.py
