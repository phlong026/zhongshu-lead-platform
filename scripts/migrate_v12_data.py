#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.config import get_settings
from apps.api.src.core.database import SessionLocal
from apps.api.src.services.migration_v12 import (
    backfill_phone_fingerprints_batch,
    preview_phone_fingerprint_backfill,
)

_RESET_CONFIRMATION = "RESET_PHONE_FINGERPRINT_CHECKPOINT"


def _validate_runtime_secret() -> tuple[str, bool]:
    settings = get_settings()
    production = settings.app_env.lower() == "production"
    secret = settings.phone_fingerprint_secret.strip()
    if production:
        if len(secret) < 32:
            raise RuntimeError("生产环境必须显式配置至少 32 位 PHONE_FINGERPRINT_SECRET")
        if secret == settings.phone_hash_secret:
            raise RuntimeError("PHONE_FINGERPRINT_SECRET 不得与 PHONE_HASH_SECRET 相同")
        return secret, True
    return secret or settings.effective_phone_fingerprint_secret, False


def _write_exit_code(
    *,
    fail_on_row_error: bool,
    totals: dict[str, int],
    last: dict[str, object],
) -> int:
    if not fail_on_row_error:
        return 0
    checkpoint_failed = last.get("checkpoint_status") == "COMPLETED_WITH_ERRORS"
    return 2 if totals["errors"] or checkpoint_failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="V1.2 T30 historical data migration")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-batches", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--confirm-reset", default="")
    parser.add_argument("--fail-on-row-error", action="store_true")
    args = parser.parse_args()

    if args.max_batches < 1:
        parser.error("--max-batches 必须大于 0")
    if args.dry_run and args.reset:
        parser.error("--dry-run 不允许与 --reset 同时使用")
    secret, production = _validate_runtime_secret()
    if production and args.reset and args.confirm_reset != _RESET_CONFIRMATION:
        parser.error(
            "生产重置检查点必须同时传入 "
            f"--confirm-reset {_RESET_CONFIRMATION}"
        )
    fail_on_row_error = args.fail_on_row_error or production

    with SessionLocal() as db:
        if args.dry_run:
            result = preview_phone_fingerprint_backfill(
                db,
                batch_size=args.batch_size,
                max_batches=args.max_batches,
                secret=secret,
            )
            print(json.dumps({"mode": "dry-run", **result.to_dict()}, ensure_ascii=False, indent=2))
            if result.truncated:
                return 3
            return 2 if fail_on_row_error and result.errors else 0

        totals = {"batches": 0, "scanned": 0, "updated": 0, "errors": 0}
        last: dict[str, object] = {}
        reset = args.reset
        for _ in range(args.max_batches):
            try:
                batch = backfill_phone_fingerprints_batch(
                    db,
                    batch_size=args.batch_size,
                    secret=secret,
                    reset=reset,
                )
                reset = False
                db.commit()
            except Exception:
                db.rollback()
                raise
            totals["batches"] += 1
            totals["scanned"] += batch.scanned
            totals["updated"] += batch.updated
            totals["errors"] += batch.errors
            last = batch.to_dict()
            if batch.complete:
                break
        else:
            print(
                json.dumps(
                    {"mode": "write", **totals, "last_batch": last, "complete": False},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 3

        payload = {"mode": "write", **totals, "last_batch": last, "complete": True}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return _write_exit_code(
            fail_on_row_error=fail_on_row_error,
            totals=totals,
            last=last,
        )


if __name__ == "__main__":
    raise SystemExit(main())
