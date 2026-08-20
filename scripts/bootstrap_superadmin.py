#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.database import SessionLocal
from apps.api.src.core.logging import configure_logging
from apps.api.src.services.superadmin_bootstrap import (
    SuperadminBootstrapError,
    bootstrap_superadmin,
)


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="在已迁移的空数据库中创建首位超级管理员",
    )
    parser.add_argument("--username", required=True, help="内部登录账号")
    parser.add_argument(
        "--display-name",
        default="平台超级管理员",
        help="后台显示名称",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    password_reader: Callable[[str], str] = getpass.getpass,
) -> int:
    args = build_parser().parse_args(argv)
    password = password_reader("输入超级管理员密码: ")
    confirmation = password_reader("再次输入密码: ")
    if password != confirmation:
        print("初始化失败：两次输入的密码不一致", file=sys.stderr)
        return 2

    with session_factory() as db:
        try:
            result = bootstrap_superadmin(
                db,
                username=args.username,
                password=password,
                display_name=args.display_name,
            )
            db.commit()
        except SuperadminBootstrapError as exc:
            db.rollback()
            print(f"初始化失败：{exc}", file=sys.stderr)
            return 1
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "superadmin bootstrap database commit failed",
                extra={"operation": "bootstrap_superadmin"},
            )
            print("初始化失败：数据库写入失败", file=sys.stderr)
            return 1

    status = "created" if result.created else "already_exists"
    print(
        json.dumps(
            {
                "status": status,
                "user_id": result.user_id,
                "username": result.username,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())
