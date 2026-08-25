from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from apps.api.src.core.models import AuditLog, Lead, Notification, User, VerificationTask
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.core.v12_enums import LeadV12Status
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.verification_service import publish_template


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def _data(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == "OK"
    return payload["data"]


def test_pre_dispatch_http_flow_never_allows_telesales_to_self_assign(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        operation = db.scalar(select(User).where(User.username == "operation"))
        telesales = db.scalar(select(User).where(User.username == "telesales"))
        assert operation is not None and telesales is not None
        other = create_internal_user(
            db,
            username="pre-http-other",
            password="simple88",
            display_name="其他电销",
            role_code="TELESALES",
        )
        lead = Lead(
            source_type="SUPPLIER_H5",
            source_kind="SUPPLIER_H5",
            customer_name="HTTP 前置核验客户",
            phone_encrypted=encrypt_text("13900139010"),
            phone_hash=hash_phone("13900139010"),
            city="上海市",
            region_code="310000",
            category_code="OLD_RENOVATION",
            need_summary="确认装修需求真实性",
            consent_confirmed=True,
            status=LeadV12Status.PENDING_REVIEW.value,
            review_status="PENDING",
            duplicate_status="CLEAR",
            raw_payload={},
        )
        db.add(lead)
        publish_template(db, code="PRE_HTTP", name="HTTP 前置核验", schema={"fields": []})
        db.commit()
        lead_id = lead.id
        telesales_id = telesales.id
        other_id = other.id

    operation_headers = _login(client, "operation", "Operation123!")
    telesales_headers = _login(client, "telesales", "Telesales123!")
    other_headers = _login(client, "pre-http-other", "simple88")
    assigned = _data(
        client.post(
            f"/api/v1/v1.2/admin/leads/{lead_id}/pre-dispatch-verification",
            headers=operation_headers,
            json={
                "assignee_user_id": telesales_id,
                "reason": "资料描述需要电话确认",
                "template_code": "PRE_HTTP",
            },
        )
    )
    task_id = assigned["id"]
    assert assigned["lead"]["phone"] is None
    assert assigned["due_at"] is not None
    with factory() as db:
        notification = db.scalar(
            select(Notification).where(
                Notification.user_id == telesales_id,
                Notification.scene == "V12_PRE_DISPATCH_VERIFY_ASSIGNED",
            )
        )
        assert notification is not None
        assert notification.deep_link == "/h5/call/#/verify"

    own_tasks = _data(client.get("/api/v1/v1.2/pre-dispatch-verifications/tasks", headers=other_headers))
    assert own_tasks["total"] == 0
    other_start = client.post(
        f"/api/v1/v1.2/pre-dispatch-verifications/tasks/{task_id}/start",
        headers=other_headers,
    )
    assert other_start.status_code == 403

    started = _data(
        client.post(
            f"/api/v1/v1.2/pre-dispatch-verifications/tasks/{task_id}/start",
            headers=telesales_headers,
        )
    )
    assert started["lead"]["phone"] == "13900139010"
    dial = _data(
        client.post(
            f"/api/v1/v1.2/pre-dispatch-verifications/tasks/{task_id}/dial",
            headers=telesales_headers,
        )
    )
    assert dial == {"phone": "13900139010", "tel_url": "tel:13900139010"}
    submitted = _data(
        client.post(
            f"/api/v1/v1.2/pre-dispatch-verifications/tasks/{task_id}/submit",
            headers=telesales_headers,
            json={
                "contact_result": "CONNECTED",
                "conclusion": "QUALIFIED",
                "note": "客户确认本人咨询，需求明确。",
            },
        )
    )
    assert submitted["result"] == "QUALIFIED"
    disposition = _data(
        client.post(
            f"/api/v1/v1.2/admin/leads/{lead_id}/pre-dispatch-disposition",
            headers=operation_headers,
            json={"decision": "APPROVE_POOL", "note": "运营确认转入派发池。"},
        )
    )
    assert disposition["status"] == LeadV12Status.READY_DISPATCH.value
    assert other_id != telesales_id


def test_overdue_pre_dispatch_task_cannot_be_dialed(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        operation = db.scalar(select(User).where(User.username == "operation"))
        telesales = db.scalar(select(User).where(User.username == "telesales"))
        assert operation is not None and telesales is not None
        replacement = create_internal_user(
            db,
            username="pre-overdue-replacement",
            password="simple88",
            display_name="超时接手电销",
            role_code="TELESALES",
        )
        lead = Lead(
            source_type="SUPPLIER_H5",
            source_kind="SUPPLIER_H5",
            customer_name="拨号超时客户",
            phone_encrypted=encrypt_text("13900139012"),
            phone_hash=hash_phone("13900139012"),
            city="上海市",
            region_code="310000",
            category_code="OLD_RENOVATION",
            need_summary="超时后不得继续拨打",
            consent_confirmed=True,
            status=LeadV12Status.PENDING_REVIEW.value,
            review_status="PENDING",
            duplicate_status="CLEAR",
            raw_payload={},
        )
        db.add(lead)
        publish_template(db, code="PRE_DIAL_OVERDUE", name="拨号超时核验", schema={"fields": []})
        db.commit()
        lead_id = lead.id
        telesales_id = telesales.id
        replacement_id = replacement.id

    operation_headers = _login(client, "operation", "Operation123!")
    telesales_headers = _login(client, "telesales", "Telesales123!")
    task = _data(
        client.post(
            f"/api/v1/v1.2/admin/leads/{lead_id}/pre-dispatch-verification",
            headers=operation_headers,
            json={
                "assignee_user_id": telesales_id,
                "reason": "请在期限内确认客户资料",
                "template_code": "PRE_DIAL_OVERDUE",
            },
        )
    )
    task_id = task["id"]
    _data(
        client.post(
            f"/api/v1/v1.2/pre-dispatch-verifications/tasks/{task_id}/start",
            headers=telesales_headers,
        )
    )
    with factory() as db:
        overdue_task = db.get(VerificationTask, task_id)
        assert overdue_task is not None
        overdue_task.due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    detail = _data(
        client.get(
            f"/api/v1/v1.2/pre-dispatch-verifications/tasks/{task_id}",
            headers=telesales_headers,
        )
    )
    assert detail["is_overdue"] is True
    assert detail["lead"]["next_owner"] == "OPERATION"
    assert detail["lead"]["phone"] is None
    dial = client.post(
        f"/api/v1/v1.2/pre-dispatch-verifications/tasks/{task_id}/dial",
        headers=telesales_headers,
    )
    assert dial.status_code == 409
    assert dial.json()["code"] == "PRE_DISPATCH_TASK_OVERDUE"

    reassigned = _data(
        client.post(
            f"/api/v1/v1.2/admin/leads/{lead_id}/pre-dispatch-verification",
            headers=operation_headers,
            json={
                "assignee_user_id": replacement_id,
                "reason": "原电销任务超时，运营重新安排核验",
                "template_code": "PRE_DIAL_OVERDUE",
            },
        )
    )
    assert reassigned["assignee_user_id"] == replacement_id
    with factory() as db:
        audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.action == "V12_PRE_DISPATCH_VERIFY_ASSIGN",
                AuditLog.resource_id == task_id,
            )
            .order_by(AuditLog.created_at.desc())
        )
        assert audit is not None
        assert audit.before_json is not None
        assert audit.before_json["assignee_user_id"] == telesales_id
        assert audit.before_json["status"] == "IN_PROGRESS"
        assert audit.before_json["due_at"] is not None
        assert audit.after_json["assignee_user_id"] == replacement_id
        assert audit.after_json["status"] == "ASSIGNED"
        assert audit.after_json["due_at"] is not None
