#!/usr/bin/env python3
"""Perform the reviewed, one-account-one-role migration without auto-promotion."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import sys

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.database import SessionLocal
from apps.api.src.core.models import Role, User, UserRole
from apps.api.src.core.role_contract import (
    ACTIVE_BUSINESS_ROLE_CODES,
    has_exactly_one_active_business_role,
)
from apps.api.src.services.audit import write_audit
from apps.api.src.services.rbac import assign_role, seed_rbac


@dataclass(frozen=True)
class AccountRoleChange:
    user_id: str
    username: str | None
    company_id: str | None
    before_roles: tuple[str, ...]
    target_role: str

    def to_dict(self) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "company_id": self.company_id,
            "before_roles": list(self.before_roles),
            "target_role": self.target_role,
        }


@dataclass(frozen=True)
class RoleMigrationPlan:
    changes: tuple[AccountRoleChange, ...]
    unresolved: tuple[AccountRoleChange, ...]
    unknown_mapping_user_ids: tuple[str, ...]
    invalid_mapping_user_ids: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not (
            self.unresolved
            or self.unknown_mapping_user_ids
            or self.invalid_mapping_user_ids
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "change_count": len(self.changes),
            "changes": [item.to_dict() for item in self.changes],
            "unresolved": [item.to_dict() for item in self.unresolved],
            "unknown_mapping_user_ids": list(self.unknown_mapping_user_ids),
            "invalid_mapping_user_ids": list(self.invalid_mapping_user_ids),
        }


def load_mapping(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取角色映射文件：{exc}") from exc
    entries = payload.get("users") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError("映射文件必须是包含 users 数组的 JSON 对象")

    mapping: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"users[{index}] 必须为对象")
        user_id = str(entry.get("user_id") or "").strip()
        target_role = str(entry.get("target_role") or "").strip().upper()
        if not user_id or target_role not in ACTIVE_BUSINESS_ROLE_CODES:
            raise ValueError(f"users[{index}] 必须包含有效的 user_id 和 target_role")
        if user_id in mapping:
            raise ValueError(f"映射文件包含重复 user_id：{user_id}")
        mapping[user_id] = target_role
    return mapping


def build_plan(db: Session, mapping: dict[str, str]) -> RoleMigrationPlan:
    users = db.scalars(select(User).options(selectinload(User.roles)).order_by(User.id)).all()
    users_by_id = {user.id: user for user in users}
    unknown_mapping_user_ids = tuple(sorted(set(mapping) - set(users_by_id)))
    changes: list[AccountRoleChange] = []
    unresolved: list[AccountRoleChange] = []
    invalid_mapping_user_ids: list[str] = []

    for user in users:
        before_roles = tuple(sorted(role.code for role in user.roles))
        target_role = mapping.get(user.id)
        if has_exactly_one_active_business_role(before_roles):
            if target_role and target_role != before_roles[0]:
                changes.append(
                    AccountRoleChange(
                        user_id=user.id,
                        username=user.username,
                        company_id=user.company_id,
                        before_roles=before_roles,
                        target_role=target_role,
                    )
                )
            continue
        if target_role is None:
            unresolved.append(
                AccountRoleChange(
                    user_id=user.id,
                    username=user.username,
                    company_id=user.company_id,
                    before_roles=before_roles,
                    target_role="",
                )
            )
            continue
        if target_role not in ACTIVE_BUSINESS_ROLE_CODES:
            invalid_mapping_user_ids.append(user.id)
            continue
        changes.append(
            AccountRoleChange(
                user_id=user.id,
                username=user.username,
                company_id=user.company_id,
                before_roles=before_roles,
                target_role=target_role,
            )
        )
    return RoleMigrationPlan(
        changes=tuple(changes),
        unresolved=tuple(unresolved),
        unknown_mapping_user_ids=unknown_mapping_user_ids,
        invalid_mapping_user_ids=tuple(sorted(invalid_mapping_user_ids)),
    )


def apply_plan(db: Session, plan: RoleMigrationPlan, *, source: str) -> None:
    if not plan.ready:
        raise ValueError("角色迁移计划未就绪；请处理所有未映射或无效账号后再应用")

    seed_rbac(db, source=f"{source}:role_migration")
    for change in plan.changes:
        user = db.scalar(
            select(User).where(User.id == change.user_id).with_for_update()
        )
        if user is None:
            raise ValueError(f"迁移期间账号不存在：{change.user_id}")
        before_roles = tuple(sorted(role.code for role in user.roles))
        if before_roles == (change.target_role,):
            continue
        db.execute(delete(UserRole).where(UserRole.user_id == user.id))
        db.flush()
        db.expire(user, ["roles"])
        assign_role(db, user, change.target_role)
        user.session_version += 1
        write_audit(
            db,
            principal=None,
            action="SYSTEM_ACCOUNT_ROLE_MIGRATION",
            resource_type="user",
            resource_id=user.id,
            company_id=user.company_id,
            before={"roles": list(before_roles), "session_version": user.session_version - 1},
            after={"roles": [change.target_role], "session_version": user.session_version},
            metadata={"source": source, "mode": "reviewed_mapping"},
        )
    db.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按人工确认的 JSON 映射将存量账号迁移到唯一五角色",
    )
    parser.add_argument("--mapping-file", type=Path, required=True, help="人工确认的 users 映射 JSON")
    parser.add_argument("--apply", action="store_true", help="写入角色映射；省略时仅 dry-run")
    parser.add_argument("--source", default="manual_cli", help="审计来源标识")
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
    try:
        mapping = load_mapping(args.mapping_file)
        with session_factory() as db:
            plan = build_plan(db, mapping)
            if args.apply:
                apply_plan(db, plan, source=source)
                db.commit()
                mode = "apply"
            else:
                mode = "dry-run"
    except (SQLAlchemyError, ValueError) as exc:
        print(json.dumps({"status": "failed", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {"status": "ok", "mode": mode, "source": source, "plan": plan.to_dict()},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
