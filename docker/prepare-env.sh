#!/bin/sh
set -eu

# docker-compose.yml passes PostgreSQL components separately. Build the SQLAlchemy
# URL inside the container so reserved characters in credentials are encoded
# exactly the same way as host-side production validation.
if [ -z "${DATABASE_URL:-}" ]; then
  export POSTGRES_USER="${POSTGRES_USER:-zhongshu}"
  export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-change-this-database-password}"
  export POSTGRES_DB="${POSTGRES_DB:-zhongshu}"
  DATABASE_URL="$(python - <<'PY'
import os
from urllib.parse import quote

user = quote(os.environ["POSTGRES_USER"], safe="")
password = quote(os.environ["POSTGRES_PASSWORD"], safe="")
database = quote(os.environ["POSTGRES_DB"], safe="")
print(f"postgresql+psycopg://{user}:{password}@db:5432/{database}")
PY
)"
  export DATABASE_URL
fi
