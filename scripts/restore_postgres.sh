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
RESTART=${RESTORE_RESTART_SERVICES:-NO}
RESTORE_SUCCEEDED=false
if [ "$MANAGE" = "true" ]; then
  compose stop api scheduler
fi
finish() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ "$MANAGE" = "true" ]; then
    if [ "$RESTORE_SUCCEEDED" = "true" ] && [ "$RESTART" = "YES" ]; then
      compose up -d api scheduler
    elif [ "$RESTORE_SUCCEEDED" = "true" ]; then
      echo "restore completed; api and scheduler remain stopped for revision, reconciliation and smoke validation" >&2
      echo "restart them manually only after post-restore gates pass" >&2
    else
      echo "restore did not complete successfully; api and scheduler remain stopped" >&2
      echo "inspect PostgreSQL, restore from a known-good backup if needed, then restart services manually" >&2
    fi
  fi
  exit "$status"
}
trap finish EXIT HUP INT TERM

# --exit-on-error makes pg_restore stop at the first SQL error instead of
# continuing into an indeterminate partially restored state.
cat "$FILE" | compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges --exit-on-error'
compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"' >/dev/null
RESTORE_SUCCEEDED=true
printf '%s\n' "restore completed: $FILE"
