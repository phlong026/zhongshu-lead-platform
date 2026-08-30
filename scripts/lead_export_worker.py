#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import signal
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.database import SessionLocal, init_database
from apps.api.src.services.lead_export_v12 import process_lead_export_tasks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lead_export_worker")
running = True
DEFAULT_HEARTBEAT_FILE = "/tmp/zhongshu-lead-export-heartbeat"


def stop(*_: object) -> None:
    global running
    running = False


def poll_interval_seconds() -> int:
    try:
        value = int(os.environ.get("LEAD_EXPORT_POLL_SECONDS", "5"))
    except ValueError:
        value = 5
    return max(1, min(value, 60))


def heartbeat_path() -> Path:
    return Path(
        os.environ.get("LEAD_EXPORT_HEARTBEAT_FILE", DEFAULT_HEARTBEAT_FILE)
    )


def clear_heartbeat(path: Path | None = None) -> None:
    (path or heartbeat_path()).unlink(missing_ok=True)


def publish_heartbeat(path: Path | None = None) -> None:
    target = path or heartbeat_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(f"{time.time()}\n", encoding="ascii")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def run_once() -> tuple[dict[str, int], bool]:
    with SessionLocal() as db:
        try:
            result = process_lead_export_tasks(
                db,
                limit=1,
                progress=publish_heartbeat,
            )
            db.commit()
            return result, True
        except Exception:
            db.rollback()
            logger.exception("lead export worker cycle failed")
            return {
                "claimed": 0,
                "completed": 0,
                "failed": 1,
                "superseded": 0,
            }, False


def main() -> int:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    clear_heartbeat()
    init_database()
    interval = poll_interval_seconds()
    while running:
        result, cycle_succeeded = run_once()
        if cycle_succeeded:
            publish_heartbeat()
        if result["completed"] or result["failed"] or result["superseded"]:
            logger.info("lead export metrics=%s", result)
        if result["claimed"]:
            continue
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)
    logger.info("lead export worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
