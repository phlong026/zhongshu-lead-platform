#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.config import get_settings

_REQUIRED_TABLES = (
    "leads",
    "assignments",
    "points_accounts",
    "points_ledgers",
    "return_requests",
    "return_evidences",
)
_STATUS_TABLES = ("leads", "assignments", "return_requests")


def collect_v101_baseline(database_url: str) -> dict[str, Any]:
    """Collect a PII-free report using only V1.0.1 tables and columns."""

    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        existing = set(inspector.get_table_names())
        missing = [table for table in _REQUIRED_TABLES if table not in existing]
        if missing:
            return {
                "valid": False,
                "errors": [{"code": "V101_TABLE_MISSING", "tables": missing}],
                "metrics": {},
            }
        metrics: dict[str, Any] = {"table_counts": {}, "status_counts": {}}
        with engine.connect() as connection:
            for table in _REQUIRED_TABLES:
                metrics["table_counts"][table] = int(
                    connection.scalar(text(f'SELECT COUNT(*) FROM "{table}"')) or 0
                )
            for table in _STATUS_TABLES:
                rows = connection.execute(
                    text(
                        f'SELECT status, COUNT(*) AS count FROM "{table}" '
                        "GROUP BY status ORDER BY status"
                    )
                ).all()
                metrics["status_counts"][table] = {
                    str(status): int(count) for status, count in rows
                }
            metrics["points_ledger_delta_sum"] = int(
                connection.scalar(text("SELECT COALESCE(SUM(delta), 0) FROM points_ledgers")) or 0
            )
            metrics["points_account_balance_sum"] = int(
                connection.scalar(text("SELECT COALESCE(SUM(balance), 0) FROM points_accounts")) or 0
            )
        return {"valid": True, "errors": [], "metrics": metrics}
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect a V1.0.1 pre-upgrade baseline without V1.2 schema dependencies")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "v101-baseline.json")
    args = parser.parse_args()
    settings = get_settings()
    report = collect_v101_baseline(settings.database_url)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
