#!/bin/sh
set -eu
if [ "${CONFIRM_RESTORE:-}" != "YES" ]; then
  echo "set CONFIRM_RESTORE=YES to confirm storage restore" >&2
  exit 2
fi
if [ "$#" -ne 1 ]; then
  echo "usage: CONFIRM_RESTORE=YES $0 <private-storage.tar.gz>" >&2
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
cat "$FILE" | compose exec -T api sh -c 'mkdir -p /app/storage && tar -C /app/storage -xzf -'
printf '%s\n' "storage restore completed: $FILE"
