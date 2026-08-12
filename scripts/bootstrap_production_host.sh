#!/bin/sh
#
# V1.2 production host bootstrap (Issue #42 / P1 infrastructure).
#
# Idempotently prepares the reference 4C8G Linux host:
#   - Docker Engine + Docker Compose plugin
#   - optional persistent data-disk mount (only formats when FORMAT_DATA_DISK=1)
#   - NTP time sync via chrony
#   - ufw host firewall (22/80/443 only; cloud security group remains primary)
#   - required directory layout under the checkout
#
# Run as root on the target host, e.g.:
#   sudo DATA_DISK_DEV=/dev/vdb DATA_DISK_MOUNT=/data sh scripts/bootstrap_production_host.sh
#
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DATA_DISK_DEV=${DATA_DISK_DEV:-}
DATA_DISK_MOUNT=${DATA_DISK_MOUNT:-/data}
FORMAT_DATA_DISK=${FORMAT_DATA_DISK:-0}

say() { printf '[bootstrap] %s\n' "$*"; }
fail() { printf '[bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "must run as root (use sudo)"

command -v apt-get >/dev/null 2>&1 || fail "this bootstrap targets Debian/Ubuntu hosts"

# --- Docker Engine + Compose plugin -------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    say "Docker and Compose plugin already present"
else
    say "installing Docker and Compose plugin"
    apt-get update
    if ! apt-get install -y docker.io docker-compose-plugin; then
        # Ubuntu 24.04 ships docker-compose-v2 instead of docker-compose-plugin
        apt-get install -y docker.io docker-compose-v2
    fi
    systemctl enable --now docker
fi
docker version >/dev/null 2>&1 || fail "docker daemon is not reachable"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is missing"
say "docker: $(docker --version)"
say "compose: $(docker compose version)"

# --- Persistent data disk ------------------------------------------------
if [ -n "$DATA_DISK_DEV" ]; then
    if mountpoint -q "$DATA_DISK_MOUNT"; then
        say "data disk already mounted at $DATA_DISK_MOUNT"
    elif [ -b "$DATA_DISK_DEV" ]; then
        mkdir -p "$DATA_DISK_MOUNT"
        if [ "$FORMAT_DATA_DISK" = "1" ]; then
            say "formatting $DATA_DISK_DEV (FORMAT_DATA_DISK=1)"
            mkfs.ext4 "$DATA_DISK_DEV"
        fi
        mount "$DATA_DISK_DEV" "$DATA_DISK_MOUNT"
        grep -q "^$DATA_DISK_DEV " /etc/fstab || printf '%s %s ext4 defaults,noatime 0 2\n' "$DATA_DISK_DEV" "$DATA_DISK_MOUNT" >> /etc/fstab
        say "mounted $DATA_DISK_DEV at $DATA_DISK_MOUNT"
    else
        fail "$DATA_DISK_DEV is not a block device"
    fi
else
    say "DATA_DISK_DEV unset; skipping data-disk setup (verify with verify_infrastructure.py)"
fi

# --- NTP -----------------------------------------------------------------
if command -v chronyc >/dev/null 2>&1; then
    say "chrony already present"
else
    say "installing chrony"
    apt-get install -y chrony
    systemctl enable --now chrony
fi
timedatectl set-ntp true >/dev/null 2>&1 || true
chronyc tracking >/dev/null 2>&1 || say "chrony installed; waiting for first sync"

# --- Host firewall (defense in depth; security group is the primary edge) -
if command -v ufw >/dev/null 2>&1; then
    ufw allow 22/tcp >/dev/null
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
    ufw --force enable >/dev/null
    say "ufw enabled: 22/80/443 only"
else
    say "ufw missing; ensure the cloud security group already restricts ports"
fi

# --- Directory layout -----------------------------------------------------
mkdir -p "$ROOT/infra/certs" "$ROOT/backups/postgres" "$ROOT/backups/objects" \
    "$ROOT/dist" "$ROOT/production-evidence"
say "directory layout ready under $ROOT"

say "bootstrap complete"