from __future__ import annotations

import pytest

from apps.api.src.core.auth import Principal
from apps.api.src.core.enums import AssignmentStatus
from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Assignment, AssignmentEvent, Company
from apps.api.src.services.auth_service import create_internal_user


def _principal(user, *permissions: str) -> Principal:
    return Principal(
        user_id=user.id,
        display_name=user.display_name,
        company_id=user.company_id,
        role_codes=frozenset(role.code for role in user.roles),
        permission_codes=frozenset(permissions),
        session_version=user.session_version,
    )


def test_owner_assignment_keeps_employee_scope_and_operator_out_of_personal_details(db) -> None:
    from apps.api.src.services.company_assignment_v12 import (
        assign_internal_employee,
        require_company_assignment_access,
    )

    company = Company(code="COLLAB", name="内部协作加盟商")
    db.add(company)
    db.flush()
    owner = create_internal_user(
        db,
        username="collab-owner",
        password="simple88",
        display_name="负责人",
        role_code="FRANCHISE_OWNER",
        company_id=company.id,
    )
    employee = create_internal_user(
        db,
        username="collab-employee",
        password="simple88",
        display_name="员工",
        role_code="FRANCHISE_EMPLOYEE",
        company_id=company.id,
    )
    other_employee = create_internal_user(
        db,
        username="collab-other",
        password="simple88",
        display_name="其他员工",
        role_code="FRANCHISE_EMPLOYEE",
        company_id=company.id,
    )
    operation = create_internal_user(
        db,
        username="collab-operation",
        password="simple88",
        display_name="运营",
        role_code="OPERATION",
    )
    assignment = Assignment(
        lead_id="lead-collab",
        company_id=company.id,
        status=AssignmentStatus.CLAIMED.value,
        points_price=100,
        assigned_by=operation.id,
        internal_assignee_user_id=owner.id,
        internal_assigned_by=owner.id,
    )
    db.add(assignment)
    db.flush()

    changed = assign_internal_employee(
        db,
        assignment_id=assignment.id,
        principal=_principal(owner, "assignment.own.read"),
        employee_user_id=employee.id,
        reason="由负责人交办首轮跟进",
    )
    assert changed.changed is True
    assert assignment.internal_assignee_user_id == employee.id
    assert require_company_assignment_access(
        _principal(employee, "assignment.employee.read"), assignment
    ) is None

    with pytest.raises(AppError) as other_scope:
        require_company_assignment_access(
            _principal(other_employee, "assignment.employee.read"), assignment
        )
    assert other_scope.value.code == "COMPANY_ASSIGNMENT_NOT_ASSIGNED"

    with pytest.raises(AppError) as operation_scope:
        require_company_assignment_access(
            _principal(operation, "assignment.read"), assignment
        )
    assert operation_scope.value.code == "FORBIDDEN"

    event = db.query(AssignmentEvent).filter_by(assignment_id=assignment.id).one()
    assert event.event_type == "V12_INTERNAL_ASSIGNMENT_ASSIGNED"
    assert event.payload == {
        "previous_employee_user_id": owner.id,
        "employee_user_id": employee.id,
        "reason": "由负责人交办首轮跟进",
    }


def test_employee_disable_requires_internal_assignment_handover(db) -> None:
    from apps.api.src.services.company_account_management import set_company_account_status

    company = Company(code="HANDOVER", name="待交接加盟商")
    db.add(company)
    db.flush()
    owner = create_internal_user(
        db,
        username="handover-owner",
        password="simple88",
        display_name="负责人",
        role_code="FRANCHISE_OWNER",
        company_id=company.id,
    )
    employee = create_internal_user(
        db,
        username="handover-employee",
        password="simple88",
        display_name="员工",
        role_code="FRANCHISE_EMPLOYEE",
        company_id=company.id,
    )
    company.primary_user_id = owner.id
    assignment = Assignment(
        lead_id="lead-handover",
        company_id=company.id,
        status=AssignmentStatus.FOLLOWING.value,
        points_price=100,
        assigned_by=owner.id,
        internal_assignee_user_id=employee.id,
        internal_assigned_by=owner.id,
    )
    db.add(assignment)
    db.flush()

    with pytest.raises(AppError) as exc_info:
        set_company_account_status(
            db,
            company_id=company.id,
            user_id=employee.id,
            status="DISABLED",
        )

    assert exc_info.value.code == "COMPANY_ACCOUNT_HANDOVER_REQUIRED"
