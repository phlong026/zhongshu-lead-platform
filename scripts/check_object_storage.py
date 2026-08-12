#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.config import get_settings  # noqa: E402
from apps.api.src.core.errors import AppError  # noqa: E402
from apps.api.src.services.storage import get_storage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check private object storage readiness")
    parser.add_argument("--canary", action="store_true", help="write, read, and delete a disposable S3 canary")
    args = parser.parse_args()
    settings = get_settings()
    storage = get_storage()
    try:
        storage.check_readiness()
        key = storage.run_canary() if args.canary else None
    except AppError as exc:
        print(json.dumps({"valid": False, "code": exc.code}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {"valid": True, "backend": settings.object_storage_backend.lower(), "canary": bool(args.canary), "canary_prefix": ".canary/zhongshu-readiness/" if key else None},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
