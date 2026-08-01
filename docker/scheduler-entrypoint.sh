#!/bin/sh
set -eu
alembic upgrade head
exec python scripts/scheduler.py
