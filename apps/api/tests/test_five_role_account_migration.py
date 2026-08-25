from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from apps.api.src.core.models import AuditLog, Role, User, UserRole
from scripts.migrate_five_role_accounts import apply_plan, build_plan


def _legacy_user(db):
    role = Role(code="FINANCE", name="历史财务", description="待迁移历史角色")
    user = User(
        username="legacy-finance",
        password_hash="not-used",
        display_name="历史财务账号",
        status="ACTIVE",
        session_version=4,
    )
    db.add_all([role, user])
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user


def test_role_migration_dry_run_requires_every_legacy_account_to_be_mapped(db) -> None:
    user = _legacy_user(db)

    plan = build_plan(db, {})

    assert plan.ready is False
    assert [item.user_id for item in plan.unresolved] == [user.id]
    assert plan.unresolved[0].before_roles == ("FINANCE",)


def test_role_migration_applies_only_the_reviewed_mapping_and_invalidates_sessions(db) -> None:
    user = _legacy_user(db)
    plan = build_plan(db, {user.id: "SUPER_ADMIN"})

    assert plan.ready is True
    assert [item.target_role for item in plan.changes] == ["SUPER_ADMIN"]

    apply_plan(db, plan, source="test_reviewed_mapping")
    db.commit()
    migrated = db.scalar(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user.id)
    )
    assert migrated is not None
    assert [role.code for role in migrated.roles] == ["SUPER_ADMIN"]
    assert migrated.session_version == 5
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "SYSTEM_ACCOUNT_ROLE_MIGRATION",
            AuditLog.resource_id == user.id,
        )
    )
    assert audit is not None
    assert audit.before_json == {"roles": ["FINANCE"], "session_version": 4}
    assert audit.after_json == {"roles": ["SUPER_ADMIN"], "session_version": 5}
