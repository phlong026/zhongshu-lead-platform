from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.core.models import Permission, Role, RolePermission
from apps.api.src.services.rbac import (
    ROLE_PERMISSION_MATRIX,
    RbacSyncRequiredError,
    preview_rbac_sync,
    require_rbac_sync_complete,
    seed_rbac,
)


MINIMUM_ROLE_PERMISSIONS = {
    "SUPER_ADMIN": {"*"},
    "OWNER": {"lead.phone.read", "points.read", "audit.read", "report.v12.read"},
    "LEAD_ENTRY": {"lead.read", "lead.manual.manage"},
    "OPERATION": {
        "lead.dispatch",
        "company.profile.review",
        "verification.read",
        "notification.retry",
    },
    "TELESALES": {
        "verification.task.read",
        "verification.task.claim",
        "verification.submit",
        "lead.phone.read",
    },
    "FINANCE": {
        "points.recharge",
        "points.reverse",
        "reward.manage",
        "reward.reverse",
    },
    "RETURN_REVIEWER": {
        "return.review",
        "return.evidence.read",
        "lead.phone.read",
    },
    "FRANCHISE_OWNER": {
        "assignment.own.claim",
        "lead.own.phone.read",
        "return.own.manage",
        "points.own.read",
    },
}


def _role(db: Session, code: str) -> Role:
    role = db.scalar(select(Role).where(Role.code == code))
    assert role is not None
    return role


def _role_permission_codes(db: Session, role_code: str) -> set[str]:
    role = _role(db, role_code)
    return set(
        db.scalars(
            select(Permission.code)
            .join(
                RolePermission,
                RolePermission.permission_id == Permission.id,
            )
            .where(RolePermission.role_id == role.id)
        ).all()
    )


def _permission(db: Session, code: str) -> Permission:
    permission = db.scalar(select(Permission).where(Permission.code == code))
    assert permission is not None
    return permission


def _remove_role_permission(
    db: Session,
    *,
    role_code: str,
    permission_code: str,
) -> None:
    role = _role(db, role_code)
    permission = _permission(db, permission_code)
    mapping = db.get(RolePermission, (role.id, permission.id))
    assert mapping is not None
    db.delete(mapping)
    db.flush()


def _add_stale_permission(db: Session, *roles: Role) -> Permission:
    stale = Permission(
        code="legacy.dangerous.permission",
        name="legacy.dangerous.permission",
        module="legacy",
        sensitive=True,
    )
    db.add(stale)
    db.flush()
    for role in roles:
        db.add(RolePermission(role_id=role.id, permission_id=stale.id))
    db.flush()
    return stale


def _role_diff(result, role_code: str):
    return next(role for role in result.roles if role.role_code == role_code)


def test_seed_rbac_adds_missing_role_permission_mapping(db: Session) -> None:
    _remove_role_permission(
        db,
        role_code="OPERATION",
        permission_code="lead.dispatch",
    )

    result = seed_rbac(db, source="test_missing_mapping")

    assert "lead.dispatch" in _role_permission_codes(db, "OPERATION")
    assert _role_diff(result, "OPERATION").added == ("lead.dispatch",)
    assert result.removed_count == 0


def test_seed_rbac_removes_stale_permission_from_fixed_role(db: Session) -> None:
    role = _role(db, "OPERATION")
    _add_stale_permission(db, role)

    result = seed_rbac(db, source="test_stale_mapping")

    assert "legacy.dangerous.permission" not in _role_permission_codes(
        db,
        "OPERATION",
    )
    assert _role_diff(result, "OPERATION").removed == (
        "legacy.dangerous.permission",
    )


def test_preview_reports_drift_without_writing(db: Session) -> None:
    operation = _role(db, "OPERATION")
    _add_stale_permission(db, operation)
    _remove_role_permission(
        db,
        role_code="OPERATION",
        permission_code="lead.dispatch",
    )

    result = preview_rbac_sync(db)

    operation_diff = _role_diff(result, "OPERATION")
    assert operation_diff.added == ("lead.dispatch",)
    assert operation_diff.removed == ("legacy.dangerous.permission",)
    assert "lead.dispatch" not in _role_permission_codes(db, "OPERATION")
    assert "legacy.dangerous.permission" in _role_permission_codes(
        db,
        "OPERATION",
    )


def test_production_gate_refuses_unreviewed_rbac_drift_without_writing(
    db: Session,
) -> None:
    operation = _role(db, "OPERATION")
    _add_stale_permission(db, operation)

    with pytest.raises(RbacSyncRequiredError) as captured:
        require_rbac_sync_complete(db, source="test_production_startup")

    assert captured.value.result.removed_count == 1
    assert "legacy.dangerous.permission" in _role_permission_codes(
        db,
        "OPERATION",
    )

    seed_rbac(db, source="test_explicit_apply")
    assert require_rbac_sync_complete(db).changed is False


def test_seed_rbac_is_idempotent_after_exact_sync(db: Session) -> None:
    operation = _role(db, "OPERATION")
    _add_stale_permission(db, operation)
    _remove_role_permission(
        db,
        role_code="OPERATION",
        permission_code="lead.dispatch",
    )

    first = seed_rbac(db, source="test_first_sync")
    second = seed_rbac(db, source="test_second_sync")

    assert first.added_count == 1
    assert first.removed_count == 1
    assert second.changed is False
    assert second.roles == ()
    assert _role_permission_codes(db, "OPERATION") == set(
        ROLE_PERMISSION_MATRIX["OPERATION"][1]
    )


def test_seed_rbac_keeps_permission_rows_and_custom_roles(db: Session) -> None:
    operation = _role(db, "OPERATION")
    custom = Role(
        code="CUSTOM_LEGACY",
        name="历史自定义角色",
        description="不属于固定角色矩阵",
        system_role=False,
    )
    db.add(custom)
    db.flush()
    stale = _add_stale_permission(db, operation, custom)

    seed_rbac(db, source="test_custom_role_boundary")

    assert db.get(Permission, stale.id) is not None
    assert "legacy.dangerous.permission" not in _role_permission_codes(
        db,
        "OPERATION",
    )
    assert _role_permission_codes(db, "CUSTOM_LEGACY") == {
        "legacy.dangerous.permission"
    }


def test_fixed_roles_match_the_code_matrix_exactly(db: Session) -> None:
    seed_rbac(db, source="test_matrix_regression")

    assert {
        role_code: _role_permission_codes(db, role_code)
        for role_code in ROLE_PERMISSION_MATRIX
    } == {
        role_code: set(permission_codes)
        for role_code, (_, permission_codes) in ROLE_PERMISSION_MATRIX.items()
    }


def test_critical_role_permissions_cannot_be_removed_silently(db: Session) -> None:
    seed_rbac(db, source="test_minimum_role_regression")

    for role_code, minimum_permissions in MINIMUM_ROLE_PERMISSIONS.items():
        assert minimum_permissions <= _role_permission_codes(db, role_code)
