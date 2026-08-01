#!/bin/sh
set -eu
if [ "${APP_ENV:-development}" = "production" ]; then
  python scripts/validate_production_env.py --quiet
fi
exec python scripts/scheduler.py
