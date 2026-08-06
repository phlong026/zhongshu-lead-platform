from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import Permission, Role, RolePermission, User, UserRole

ROLE_PERMISSION_MATRIX: dict[str, tuple[str, list[str]]] = {
    "SUPER_ADMIN": ("超级管理员", ["*"]),
    "OWNER": (
        "老板/业务负责人",
        [
            "dashboard.business.read",
            "dashboard.finance.read",
            "lead.read",
            "lead.phone.read",
            "company.read",
            "assignment.read",
            "points.read",
            "return.read",
            "audit.read",
        ],
    ),
    "LEAD_ENTRY": (
        "平台客资录入员",
        [
            "lead.read",
            "lead.manual.manage",
        ],
    ),
    "OPERATION": (
        "运营人员",
        [
            "lead.read",
            "lead.edit",
            "lead.manual.manage",
            "lead.supplier.review",
            "lead.dedup.override",
            "lead.dispatch",
            "assignment.read",
            "assignment.release",
            "company.read_eligibility",
            "company.profile.review",
            "verification.read",
            "return.read",
            "notification.retry",
            "dashboard.operation.read",
        ],
    ),
    "TELESALES": (
        "电销人员",
        [
            "verification.task.read",
            "verification.task.claim",
            "verification.submit",
            "lead.phone.read",
            "lead.phone.dial",
            "dashboard.telesales.read",
        ],
    ),
    "FINANCE": (
        "积分/财务管理员",
        [
            "points.read",
            "points.package.manage",
            "points.recharge",
            "points.reverse",
            "dashboard.finance.read",
            "company.read",
        ],
    ),
    "RETURN_REVIEWER": (
        "退回审核员",
        ["return.read", "return.review", "return.evidence.read", "lead.phone.read"],
    ),
    "FRANCHISE_OWNER": (
        "加盟商负责人",
        [
            "h5.home",
            "assignment.own.read",
            "assignment.own.claim",
            "lead.own.phone.read",
            "supplier.lead.manage",
            "company.profile.manage",
            "followup.own.manage",
            "return.own.manage",
            "points.own.read",
            "notification.own.read",
        ],
    ),
}


def seed_rbac(db: Session) -> None:
    permission_cache: dict[str, Permission] = {}
    all_codes = {code for _, codes in ROLE_PERMISSION_MATRIX.values() for code in codes}
    for code in sorted(all_codes):
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if not permission:
            module = code.split(".", 1)[0] if code != "*" else "system"
            permission = Permission(code=code, name=code, module=module, sensitive=code in {"*", "lead.phone.read", "points.recharge", "points.reverse", "lead.dedup.override"})
            db.add(permission)
            db.flush()
        permission_cache[code] = permission

    for role_code, (role_name, codes) in ROLE_PERMISSION_MATRIX.items():
        role = db.scalar(select(Role).where(Role.code == role_code))
        if not role:
            role = Role(code=role_code, name=role_name, description=role_name)
            db.add(role)
            db.flush()
        existing = set(
            db.scalars(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
            ).all()
        )
        for code in codes:
            if code not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission_cache[code].id))
    db.flush()


def assign_role(db: Session, user: User, role_code: str) -> None:
    role = db.scalar(select(Role).where(Role.code == role_code))
    if not role:
        raise ValueError(f"role not seeded: {role_code}")
    exists = db.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id))
    if not exists:
        db.add(UserRole(user_id=user.id, role_id=role.id))
