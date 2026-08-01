#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT/.env}
BACKUP_DIR=${BACKUP_DIR:-$ROOT/backups/private-storage}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/private-storage-$TIMESTAMP.tar.gz"
compose() {
  docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.prod.yml" "$@"
}
compose exec -T api sh -c 'tar -C /app/storage -czf - .' > "$FILE"
[ -s "$FILE" ] || { echo "storage backup is empty" >&2; rm -f "$FILE"; exit 1; }
sha256sum "$FILE" > "$FILE.sha256"
find "$BACKUP_DIR" -type f \( -name '*.tar.gz' -o -name '*.tar.gz.sha256' \) -mtime "+$RETENTION_DAYS" -delete
printf '%s\n' "$FILE"
