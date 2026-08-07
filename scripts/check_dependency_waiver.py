#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone

WAIVER_ID = "PYSEC-2026-3552"
WAIVER_EXPIRES_ON = date(2026, 8, 21)


def validate_waiver(today: date | None = None) -> dict[str, object]:
    current = today or datetime.now(timezone.utc).date()
    if current > WAIVER_EXPIRES_ON:
        raise RuntimeError(
            f"temporary dependency waiver {WAIVER_ID} expired on {WAIVER_EXPIRES_ON.isoformat()}; "
            "remove the waiver and upgrade cryptography before continuing"
        )
    return {
        "valid": True,
        "waiver_id": WAIVER_ID,
        "checked_on": current.isoformat(),
        "expires_on": WAIVER_EXPIRES_ON.isoformat(),
        "days_remaining": (WAIVER_EXPIRES_ON - current).days,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail CI after the approved dependency-waiver expiry date")
    parser.add_argument(
        "--today",
        help="optional YYYY-MM-DD override for deterministic tests/operations; default is current UTC date",
    )
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else None
    try:
        payload = validate_waiver(today)
    except RuntimeError as exc:
        payload = {
            "valid": False,
            "waiver_id": WAIVER_ID,
            "expires_on": WAIVER_EXPIRES_ON.isoformat(),
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
