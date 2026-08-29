from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from apps.api.src.core.enums import AssignmentStatus
from apps.api.src.core.models import (
    Assignment,
    Company,
    Lead,
    Notification,
    PointsAccount,
    ReturnRequest,
    User,
    VerificationTask,
)
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.core.v12_enums import LeadV12Status, VerificationTaskType
from apps.api.src.services.audit import write_audit
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.dispatch_v12 import list_candidates


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def _notification_items(client, headers: dict[str, str]) -> list[dict]:
    response = client.get(
        "/api/v1/notifications?page=1&page_size=100",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


def test_legacy_dashboard_rejects_employee_and_telesales(api_client) -> None:
    client, _factory = api_client
    employee = _login(client, "franchise_employee_demo", "Employee123!")
    telesales = _login(client, "telesales", "Telesales123!")

    for headers in (employee, telesales):
        assert client.get("/api/v1/dashboard/summary", headers=headers).status_code == 403
        assert client.get("/api/v1/dashboard/alerts", headers=headers).status_code == 403

    operation = _login(client, "operation", "Operation123!")
    admin = _login(client, "admin", "Admin123!")
    for headers in (operation, admin):
        assert client.get("/api/v1/dashboard/summary", headers=headers).status_code == 200
        assert client.get("/api/v1/dashboard/alerts", headers=headers).status_code == 200


def test_return_submitter_keeps_record_and_evidence_access_after_reassignment(
    api_client,
) -> None:
    client, factory = api_client
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        owner = db.scalar(select(User).where(User.username == "franchise_demo"))
        operator = db.scalar(select(User).where(User.username == "operation"))
        assert company is not None and owner is not None and operator is not None
        submitter = create_internal_user(
            db,
            username="return-original-submitter",
            password="Employee123!",
            display_name="退回原提交员工",
            role_code="FRANCHISE_EMPLOYEE",
            company_id=company.id,
        )
        new_assignee = create_internal_user(
            db,
            username="return-new-assignee",
            password="Employee123!",
            display_name="退回新处理员工",
            role_code="FRANCHISE_EMPLOYEE",
            company_id=company.id,
        )
        lead = Lead(
            source_type="PLATFORM_MANUAL",
            source_kind="PLATFORM_MANUAL",
            customer_name="退回权限客户",
            phone_encrypted=encrypt_text("13900139201"),
            phone_hash=hash_phone("13900139201"),
            status=LeadV12Status.CLAIMED.value,
            review_status="APPROVED",
            imported_at=datetime.now(timezone.utc),
        )
        db.add(lead)
        db.flush()
        assignment = Assignment(
            lead_id=lead.id,
            company_id=company.id,
            status=AssignmentStatus.RETURN_PENDING.value,
            points_price=100,
            assigned_by=operator.id,
            internal_assignee_user_id=new_assignee.id,
            internal_assigned_by=owner.id,
            claimed_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(assignment)
        db.flush()
        return_request = ReturnRequest(
            assignment_id=assignment.id,
            lead_id=lead.id,
            company_id=company.id,
            submitted_by=submitter.id,
            reason_code="EMPTY_NUMBER",
            reason_version=1,
            description="原提交人需要继续补证",
            status="NEED_MORE_EVIDENCE",
            due_at=datetime.now(timezone.utc) + timedelta(days=2),
            appeal_deadline_at=datetime.now(timezone.utc) + timedelta(days=2),
            submitted_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(return_request)
        db.commit()
        return_id = return_request.id

    headers = _login(client, "return-original-submitter", "Employee123!")
    listed = client.get("/api/v1/v1.2/returns?page=1&page_size=20", headers=headers)
    detail = client.get(f"/api/v1/v1.2/returns/{return_id}", headers=headers)
    evidence = client.post(
        f"/api/v1/v1.2/returns/{return_id}/evidence",
        headers=headers,
        data={"evidence_type": "CHAT_SCREENSHOT"},
        files={"file": ("proof.png", b"\x89PNG\r\n\x1a\nproof", "image/png")},
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["items"][0]["id"] == return_id
    assert detail.status_code == 200, detail.text
    assert evidence.status_code == 200, evidence.text
    resubmitted = client.post(
        f"/api/v1/v1.2/returns/{return_id}/submit",
        headers=headers,
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["data"]["status"] == "VERIFYING"
    with factory() as db:
        tasks = db.scalars(
            select(VerificationTask).where(
                VerificationTask.return_request_id == return_id,
                VerificationTask.task_type == VerificationTaskType.RETURN_VERIFY.value,
            )
        ).all()
        assert len(tasks) == 1


def test_unrelated_employee_is_rejected_before_return_evidence_storage(
    api_client,
    monkeypatch,
) -> None:
    import apps.api.src.routers.v12_returns as returns_router

    client, factory = api_client
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        owner = db.scalar(select(User).where(User.username == "franchise_demo"))
        employee = db.scalar(
            select(User).where(User.username == "franchise_employee_demo")
        )
        operator = db.scalar(select(User).where(User.username == "operation"))
        assert (
            company is not None
            and owner is not None
            and employee is not None
            and operator is not None
        )
        lead = Lead(
            source_type="PLATFORM_MANUAL",
            source_kind="PLATFORM_MANUAL",
            customer_name="退回证据越权客户",
            phone_encrypted=encrypt_text("13900139205"),
            phone_hash=hash_phone("13900139205"),
            status=LeadV12Status.CLAIMED.value,
            review_status="APPROVED",
            imported_at=datetime.now(timezone.utc),
        )
        db.add(lead)
        db.flush()
        assignment = Assignment(
            lead_id=lead.id,
            company_id=company.id,
            status=AssignmentStatus.RETURN_PENDING.value,
            points_price=100,
            assigned_by=operator.id,
            internal_assignee_user_id=owner.id,
            internal_assigned_by=owner.id,
            claimed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(assignment)
        db.flush()
        return_request = ReturnRequest(
            assignment_id=assignment.id,
            lead_id=lead.id,
            company_id=company.id,
            submitted_by=owner.id,
            reason_code="EMPTY_NUMBER",
            reason_version=1,
            description="验证权限校验发生在文件保存前",
            status="NEED_MORE_EVIDENCE",
            due_at=datetime.now(timezone.utc) + timedelta(days=2),
            appeal_deadline_at=datetime.now(timezone.utc) + timedelta(days=2),
            submitted_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        db.add(return_request)
        db.commit()
        return_id = return_request.id

    saved_objects: list[str] = []

    class RecordingStorage:
        def save(self, content, *, prefix, filename, mime_type):
            saved_objects.append(prefix)
            return SimpleNamespace(
                object_key=f"{prefix}/{filename}",
                size=len(content),
                sha256="0" * 64,
                mime_type=mime_type,
            )

    monkeypatch.setattr(returns_router, "get_storage", lambda: RecordingStorage())
    employee_headers = _login(client, "franchise_employee_demo", "Employee123!")
    response = client.post(
        f"/api/v1/v1.2/returns/{return_id}/evidence",
        headers=employee_headers,
        data={"evidence_type": "CHAT_SCREENSHOT"},
        files={"file": ("proof.png", b"\x89PNG\r\n\x1a\nproof", "image/png")},
    )

    assert response.status_code == 403, response.text
    assert saved_objects == []


def test_company_notifications_are_recipient_scoped_and_read_independently(
    api_client,
) -> None:
    client, factory = api_client
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        owner = db.scalar(select(User).where(User.username == "franchise_demo"))
        assert company is not None and owner is not None
        related_employee = create_internal_user(
            db,
            username="notification-related-employee",
            password="Employee123!",
            display_name="消息相关员工",
            role_code="FRANCHISE_EMPLOYEE",
            company_id=company.id,
        )
        unrelated_employee = create_internal_user(
            db,
            username="notification-unrelated-employee",
            password="Employee123!",
            display_name="消息无关员工",
            role_code="FRANCHISE_EMPLOYEE",
            company_id=company.id,
        )
        lead = Lead(
            source_type="SUPPLIER_H5",
            source_kind="SUPPLIER_H5",
            supplier_company_id=company.id,
            submitter_user_id=related_employee.id,
            customer_name="消息隔离客户",
            phone_encrypted=encrypt_text("13900139202"),
            phone_hash=hash_phone("13900139202"),
            status=LeadV12Status.READY_DISPATCH.value,
            review_status="APPROVED",
            submitted_at=datetime.now(timezone.utc),
            imported_at=datetime.now(timezone.utc),
        )
        db.add(lead)
        db.flush()
        write_audit(
            db,
            principal=None,
            action="V12_SUPPLIER_LEAD_SUBMIT",
            resource_type="lead",
            resource_id=lead.id,
            company_id=company.id,
            after={"status": lead.status, "submitted_at": lead.submitted_at.isoformat()},
            request_id="notification-recipient-scope",
        )
        db.commit()
        scene = "V12_SUPPLIER_LEAD_SUBMITTED"

    owner_headers = _login(client, "franchise_demo", "Franchise123!")
    related_headers = _login(client, "notification-related-employee", "Employee123!")
    unrelated_headers = _login(client, "notification-unrelated-employee", "Employee123!")
    owner_items = [item for item in _notification_items(client, owner_headers) if item["scene"] == scene]
    related_items = [item for item in _notification_items(client, related_headers) if item["scene"] == scene]
    unrelated_items = [item for item in _notification_items(client, unrelated_headers) if item["scene"] == scene]

    assert len(owner_items) == 1
    assert len(related_items) == 1
    assert unrelated_items == []
    assert owner_items[0]["id"] != related_items[0]["id"]

    marked = client.post(
        f"/api/v1/notifications/{related_items[0]['id']}/read",
        headers=related_headers,
    )
    assert marked.status_code == 200, marked.text
    refreshed_owner = [
        item for item in _notification_items(client, owner_headers) if item["scene"] == scene
    ]
    assert refreshed_owner[0]["read_at"] is None

    with factory() as db:
        rows = db.scalars(select(Notification).where(Notification.scene == scene)).all()
        assert {row.user_id for row in rows} == {owner.id, related_employee.id}


def test_candidate_api_is_bounded_and_supports_server_search(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        operation = db.scalar(select(User).where(User.username == "operation"))
        assert operation is not None
        lead = Lead(
            source_type="PLATFORM_MANUAL",
            source_kind="PLATFORM_MANUAL",
            submitter_user_id=operation.id,
            customer_name="候选分页客户",
            phone_encrypted=encrypt_text("13900139203"),
            phone_hash=hash_phone("13900139203"),
            region_code="310115",
            status=LeadV12Status.READY_DISPATCH.value,
            review_status="APPROVED",
            imported_at=datetime.now(timezone.utc),
        )
        db.add(lead)
        for index in range(25):
            company = Company(
                code=f"CANDIDATE-{index:02d}",
                name=(
                    "Z大小写候选"
                    if index == 0
                    else "a大小写候选"
                    if index == 1
                    else f"候选规模公司{index:02d}"
                ),
                status="ACTIVE",
            )
            db.add(company)
            db.flush()
            db.add_all(
                [
                    PointsAccount(company_id=company.id, balance=1000),
                    CompanyServiceAreaV12(
                        company_id=company.id,
                        region_code="310115",
                        region_level="DISTRICT",
                        active=True,
                        review_status="APPROVED",
                    ),
                ]
            )
        eligible_company = Company(
            code="CANDIDATE-ELIGIBLE-LAST",
            name="最终可派发公司",
            status="ACTIVE",
        )
        db.add(eligible_company)
        db.flush()
        db.add_all(
            [
                PointsAccount(company_id=eligible_company.id, balance=1000),
                CompanyLeadCapability(
                    company_id=eligible_company.id,
                    capability_code="LEAD_RECEIVER",
                    active=True,
                    review_status="APPROVED",
                ),
                CompanyServiceAreaV12(
                    company_id=eligible_company.id,
                    region_code="310115",
                    region_level="DISTRICT",
                    active=True,
                    review_status="APPROVED",
                ),
            ]
        )
        db.commit()
        lead_id = lead.id

    operation_headers = _login(client, "operation", "Operation123!")
    first_page = client.get(
        f"/api/v1/v1.2/dispatch-pool/{lead_id}/candidates",
        headers=operation_headers,
    )
    searched = client.get(
        f"/api/v1/v1.2/dispatch-pool/{lead_id}/candidates",
        headers=operation_headers,
        params={"keyword": "候选规模公司24", "page": 1, "page_size": 20},
    )

    assert first_page.status_code == 200, first_page.text
    first_data = first_page.json()["data"]
    assert len(first_data["candidates"]) == 20
    assert first_data["total"] >= 26
    assert first_data["page"] == 1
    assert first_data["page_size"] == 20
    assert first_data["has_more"] is True
    assert first_data["page_eligible_count"] == sum(
        1 for item in first_data["candidates"] if item["eligible"]
    )
    assert "eligible_count" not in first_data
    assert "最终可派发公司" in {
        item["company_name"] for item in first_data["candidates"]
    }
    all_candidates = list(first_data["candidates"])
    current_page = first_data
    next_page = 2
    while current_page["has_more"]:
        response = client.get(
            f"/api/v1/v1.2/dispatch-pool/{lead_id}/candidates",
            headers=operation_headers,
            params={"page": next_page, "page_size": 20},
        )
        assert response.status_code == 200, response.text
        current_page = response.json()["data"]
        all_candidates.extend(current_page["candidates"])
        next_page += 1
        assert next_page <= 20
    assert len(all_candidates) == first_data["total"]
    assert len({item["company_id"] for item in all_candidates}) == len(all_candidates)
    target_index = next(
        index
        for index, item in enumerate(all_candidates)
        if item["company_name"] == "最终可派发公司"
    )
    blocked_indices = [
        index
        for index, item in enumerate(all_candidates)
        if item["company_name"].startswith("候选规模公司")
    ]
    assert blocked_indices
    assert target_index < min(blocked_indices)

    with factory() as db:
        expected_order = [
            item.company_id
            for item in list_candidates(db, lead=db.get(Lead, lead_id))
        ]
    one_by_one: list[str] = []
    page_number = 1
    while len(one_by_one) < first_data["total"]:
        response = client.get(
            f"/api/v1/v1.2/dispatch-pool/{lead_id}/candidates",
            headers=operation_headers,
            params={"page": page_number, "page_size": 1},
        )
        assert response.status_code == 200, response.text
        page_data = response.json()["data"]
        one_by_one.extend(item["company_id"] for item in page_data["candidates"])
        page_number += 1
        assert page_number <= 100
    assert one_by_one == expected_order

    assert searched.status_code == 200, searched.text
    search_data = searched.json()["data"]
    assert search_data["total"] == 1
    assert [item["company_name"] for item in search_data["candidates"]] == [
        "候选规模公司24"
    ]


def test_candidate_ui_uses_server_search_and_load_more() -> None:
    source = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    assert "candidate-load-more" in source
    assert "page_size:20,keyword" in source


def test_return_verification_does_not_inflate_pre_dispatch_todos(api_client) -> None:
    client, factory = api_client
    operation_headers = _login(client, "operation", "Operation123!")
    before_response = client.get(
        "/api/v1/v1.2/reports/overview",
        headers=operation_headers,
    )
    assert before_response.status_code == 200, before_response.text
    before = before_response.json()["data"]["management"]

    with factory() as db:
        operation = db.scalar(select(User).where(User.username == "operation"))
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        assert operation is not None and company is not None
        lead = Lead(
            source_type="PLATFORM_MANUAL",
            source_kind="PLATFORM_MANUAL",
            customer_name="退回核验待办客户",
            phone_encrypted=encrypt_text("13900139204"),
            phone_hash=hash_phone("13900139204"),
            status=LeadV12Status.CLAIMED.value,
            review_status="APPROVED",
            imported_at=datetime.now(timezone.utc),
        )
        db.add(lead)
        db.flush()
        assignment = Assignment(
            lead_id=lead.id,
            company_id=company.id,
            status=AssignmentStatus.RETURN_PENDING.value,
            points_price=100,
            assigned_by=operation.id,
        )
        db.add(assignment)
        db.flush()
        return_request = ReturnRequest(
            assignment_id=assignment.id,
            lead_id=lead.id,
            company_id=company.id,
            reason_code="EMPTY_NUMBER",
            reason_version=1,
            description="验证退回核验不混入前置待办",
            status="VERIFYING",
            submitted_by=company.primary_user_id,
        )
        db.add(return_request)
        db.flush()
        task = VerificationTask(
            lead_id=lead.id,
            template_version=1,
            status="IN_PROGRESS",
            task_type=VerificationTaskType.RETURN_VERIFY.value,
            return_request_id=return_request.id,
            assignment_id=assignment.id,
            due_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.add(task)
        db.commit()

    after_response = client.get(
        "/api/v1/v1.2/reports/overview",
        headers=operation_headers,
    )
    assert after_response.status_code == 200, after_response.text
    after = after_response.json()["data"]["management"]

    assert after["verification"] == before["verification"]
    assert after["return_verification"]["in_progress"] == (
        before["return_verification"]["in_progress"] + 1
    )
    assert after["return_verification"]["overdue"] == (
        before["return_verification"]["overdue"] + 1
    )


def test_operation_home_links_return_verification_todos_to_returns() -> None:
    source = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    assert "management.return_verification||{}" in source
    assert "['退回核验中'" in source
    assert "'rotate-ccw','?view=returns'" in source
