#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.database import SessionLocal
from apps.api.src.services.reconciliation_v12 import reconcile_v12


def main() -> int:
    parser = argparse.ArgumentParser(description="V1.2 production data reconciliation")
    parser.add_argument(
        "--allow-incomplete-backfill",
        action="store_true",
        help="Only for pre-migration baseline reports; production Go/No-Go must not use this option.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with SessionLocal() as db:
        report = reconcile_v12(
            db,
            require_completed_backfill=not args.allow_incomplete_backfill,
        )
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if report.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
