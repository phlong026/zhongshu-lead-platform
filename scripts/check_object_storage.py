#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.config import get_settings  # noqa: E402
from apps.api.src.core.errors import AppError  # noqa: E402
from apps.api.src.services.storage import ObjectStorage, get_storage  # noqa: E402


def _run_file_canary(
    storage: ObjectStorage,
    *,
    prefix: str,
    suffix: str,
    mime_type: str,
) -> str:
    content = b"zhongshu-storage-business-canary-v1"
    object_key = f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"
    try:
        with tempfile.TemporaryDirectory(prefix="zhongshu-storage-canary-") as temp_name:
            source = Path(temp_name) / f"canary{suffix}"
            source.write_bytes(content)
            storage.save_file(
                source,
                prefix=prefix,
                filename=source.name,
                mime_type=mime_type,
                object_key=object_key,
            )
            if b"".join(storage.iter_read(object_key)) != content:
                raise AppError(
                    "STORAGE_BUSINESS_CANARY_INVALID",
                    "对象存储业务路径 canary 内容校验失败",
                    503,
                )
            return object_key
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "STORAGE_BUSINESS_CANARY_FAILED",
            "对象存储业务路径 canary 失败",
            503,
        ) from exc
    finally:
        try:
            storage.delete(object_key)
        except Exception as exc:
            raise AppError(
                "STORAGE_BUSINESS_CANARY_CLEANUP_FAILED",
                "对象存储业务路径 canary 清理失败",
                503,
            ) from exc


def run_canaries(
    storage: ObjectStorage,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    checked_at = now or datetime.now(timezone.utc)
    period = checked_at.strftime("%Y/%m")
    return {
        "readiness": storage.run_canary(),
        "evidence": _run_file_canary(
            storage,
            prefix=f"evidence/v1.2/{period}/.canary",
            suffix=".bin",
            mime_type="application/octet-stream",
        ),
        "lead_exports": _run_file_canary(
            storage,
            prefix=f"lead-exports/{period}/.canary",
            suffix=".xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check private object storage readiness")
    parser.add_argument("--canary", action="store_true", help="write, read, and delete a disposable S3 canary")
    args = parser.parse_args()
    settings = get_settings()
    storage = get_storage()
    try:
        storage.check_readiness()
        canary_keys = run_canaries(storage) if args.canary else {}
    except AppError as exc:
        print(json.dumps({"valid": False, "code": exc.code}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "valid": True,
                "backend": settings.object_storage_backend.lower(),
                "canary": bool(args.canary),
                "canary_prefix": ".canary/zhongshu-readiness/" if canary_keys else None,
                "business_canary_prefixes": (
                    ["evidence/v1.2/<year>/<month>/", "lead-exports/<year>/<month>/"]
                    if canary_keys
                    else []
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
