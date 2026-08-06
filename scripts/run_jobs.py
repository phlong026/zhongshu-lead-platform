#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import json

from apps.api.src.core.database import SessionLocal, init_database
from apps.api.src.services.claim_service import run_assignment_timeouts
from apps.api.src.services.followup_service import run_followup_overdue
from apps.api.src.services.feishu_sync_service import fetch_and_import_feishu, writeback_feishu_results
from apps.api.src.services.outbox_worker import process_outbox
from apps.api.src.services.points_service import run_low_points_warnings
from apps.api.src.services.supplier_reward_v12 import drain_due_supplier_reward_settlement


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one scheduled job safely")
    parser.add_argument(
        "job",
        choices=[
            "assignment-timeouts",
            "followup-overdue",
            "low-points",
            "outbox",
            "feishu-sync",
            "supplier-rewards",
            "all",
        ],
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-batches", type=int, default=20)
    args = parser.parse_args()
    init_database()
    output: dict[str, object] = {}
    with SessionLocal() as db:
        if args.job in {"assignment-timeouts", "all"}:
            output["assignment_timeouts"] = run_assignment_timeouts(db)
        if args.job in {"followup-overdue", "all"}:
            output["followup_overdue"] = run_followup_overdue(db)
        if args.job in {"low-points", "all"}:
            output["low_points"] = run_low_points_warnings(db)
        if args.job in {"outbox", "all"}:
            output["outbox"] = process_outbox(db, limit=args.limit)
        if args.job in {"supplier-rewards", "all"}:
            output["supplier_rewards"] = drain_due_supplier_reward_settlement(
                db,
                batch_size=args.limit,
                max_batches=args.max_batches,
            )
        if args.job == "feishu-sync":
            batch, records = fetch_and_import_feishu(db)
            db.commit()
            output["feishu_sync"] = {
                "batch_id": batch.id,
                "total": batch.total_count,
                "success": batch.success_count,
                "errors": batch.error_count,
                "writeback": writeback_feishu_results(db, records),
            }
        db.commit()
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
