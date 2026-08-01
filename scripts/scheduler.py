#!/usr/bin/env python3
from __future__ import annotations

import logging
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.database import SessionLocal, init_database
from apps.api.src.services.claim_service import run_assignment_timeouts
from apps.api.src.services.followup_service import run_followup_overdue
from apps.api.src.services.outbox_worker import process_outbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")
running = True


def stop(*_: object) -> None:
    global running
    running = False


def run_cycle(run_slow_jobs: bool) -> None:
    with SessionLocal() as db:
        try:
            outbox = process_outbox(db, limit=200)
            if run_slow_jobs:
                timeouts = run_assignment_timeouts(db)
                overdue = run_followup_overdue(db)
                logger.info("cycle outbox=%s timeouts=%s followup_overdue=%s", outbox, timeouts, overdue)
            elif outbox.get("sent") or outbox.get("failed"):
                logger.info("outbox=%s", outbox)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("scheduler cycle failed")


def main() -> int:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    init_database()
    tick = 0
    while running:
        run_cycle(run_slow_jobs=tick % 10 == 0)
        tick += 1
        for _ in range(30):
            if not running:
                break
            time.sleep(1)
    logger.info("scheduler stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
