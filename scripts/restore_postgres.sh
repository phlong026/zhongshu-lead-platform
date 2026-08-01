#!/bin/sh
set -eu
if [ "${CONFIRM_RESTORE:-}" != "YES" ]; then
  echo "set CONFIRM_RESTORE=YES to confirm destructive restore" >&2
  exit 2
fi
if [ "$#" -ne 1 ]; then
  echo "usage: CONFIRM_RESTORE=YES $0 <backup.dump>" >&2
  exit 2
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT/.env}
FILE=$1
[ -f "$FILE" ] || { echo "backup not found: $FILE" >&2; exit 1; }
if [ -f "$FILE.sha256" ]; then
  (cd "$(dirname "$FILE")" && sha256sum -c "$(basename "$FILE").sha256")
fi
compose() {
  docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.prod.yml" "$@"
}
MANAGE=${RESTORE_MANAGE_SERVICES:-true}
if [ "$MANAGE" = "true" ]; then
  compose stop api scheduler
fi
restore_services() {
  if [ "$MANAGE" = "true" ]; then
    compose up -d api scheduler
  fi
}
trap restore_services EXIT
cat "$FILE" | compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges'
compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"' >/dev/null
printf '%s\n' "restore completed: $FILE"
