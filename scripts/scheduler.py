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
from apps.api.src.services.assignment_timeout_v12 import run_assignment_timeouts_active
from apps.api.src.services.followup_service import run_followup_overdue
from apps.api.src.services.notification_v12 import drain_due_supplier_reward_settlement_notified
from apps.api.src.services.outbox_worker import process_outbox
from apps.api.src.services.points_service import run_low_points_warnings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")
running = True


def stop(*_: object) -> None:
    global running
    running = False


def run_cycle(run_slow_jobs: bool, run_hourly_jobs: bool) -> None:
    with SessionLocal() as db:
        try:
            outbox = process_outbox(db, limit=200)
            metrics: dict[str, object] = {"outbox": outbox}
            if run_slow_jobs:
                metrics.update(
                    {
                        "timeouts": run_assignment_timeouts_active(db),
                        "followup_overdue": run_followup_overdue(db),
                        "low_points": run_low_points_warnings(db),
                    }
                )
            if run_hourly_jobs:
                metrics["supplier_rewards"] = drain_due_supplier_reward_settlement_notified(
                    db,
                    batch_size=500,
                    max_batches=20,
                    settled_by=None,
                )
            if run_slow_jobs or run_hourly_jobs or outbox.get("sent") or outbox.get("failed"):
                logger.info("cycle metrics=%s", metrics)
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
        run_cycle(
            run_slow_jobs=tick % 10 == 0,
            run_hourly_jobs=tick % 120 == 0,
        )
        tick += 1
        for _ in range(30):
            if not running:
                break
            time.sleep(1)
    logger.info("scheduler stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
