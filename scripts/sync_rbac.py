#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import json
import logging
from pathlib import Path
import sys

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.database import SessionLocal
from apps.api.src.core.logging import configure_logging
from apps.api.src.services.audit import write_audit
from apps.api.src.services.rbac import preview_rbac_sync, seed_rbac


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="预览或应用代码定义的固定角色权限矩阵",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="应用差异；省略时只读预览，不修改数据库",
    )
    parser.add_argument(
        "--source",
        default="manual_cli",
        help="写入审计的执行来源标识",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source = args.source.strip()
    if not source or len(source) > 128:
        parser.error("--source 必须为 1 到 128 个非空字符")

    with session_factory() as db:
        try:
            if args.apply:
                result = seed_rbac(db, source=source)
                if result.changed:
                    write_audit(
                        db,
                        principal=None,
                        action="SYSTEM_RBAC_SYNC",
                        resource_type="rbac",
                        resource_id="fixed-role-matrix",
                        after=result.to_dict(),
                        metadata={"mode": "apply", "source": source},
                    )
                db.commit()
                mode = "apply"
            else:
                result = preview_rbac_sync(db)
                mode = "preview"
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "RBAC matrix synchronization failed",
                extra={"mode": "apply" if args.apply else "preview", "source": source},
            )
            print(
                json.dumps(
                    {
                        "mode": "apply" if args.apply else "preview",
                        "status": "failed",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1

    print(
        json.dumps(
            {
                "mode": mode,
                "source": source,
                "result": result.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    configure_logging(stream=sys.stderr)
    raise SystemExit(main())
