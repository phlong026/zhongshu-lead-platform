from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from apps.api.src.core.enums import AssignmentStatus
from apps.api.src.core.models import Assignment, AuditLog, Company, FollowUp, Lead, User
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_phone
from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status


ADMIN_WORKBENCH = Path("apps/admin/public/v12-operations.js")
H5_WORKBENCH = Path("apps/h5/public/v12-workbench.js")


def _function_slice(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_item_1_company_assignment_rows_open_full_lead_detail() -> None:
    source = ADMIN_WORKBENCH.read_text(encoding="utf-8")
    history = _function_slice(
        source,
        "async function companyAssignmentHistory",
        "function changeCompanyLifecycle",
    )

    assert "data-company-assignment-detail" in history
    assert "item.lead_id" in history
    assert "openLeadDetail" in history


def test_item_2_assignment_list_separates_receipt_and_followup_status() -> None:
    source = H5_WORKBENCH.read_text(encoding="utf-8")
    assignment_list = _function_slice(
        source,
        "async function assignments()",
        "async function assignmentDetail",
    )

    assert "接收确认" in assignment_list
    assert "当前跟进" in assignment_list
    assert "receive_confirmation_status" in assignment_list
    assert "current_follow_status" in assignment_list


def test_item_2_historical_assignment_uses_its_own_latest_followup(api_client) -> None:
    client, factory = api_client
    now = datetime.now(timezone.utc)
    with factory() as db:
        operation = db.scalar(select(User).where(User.username == "operation"))
        current_company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        assert operation is not None and current_company is not None
        historical_company = Company(code="ITEM2-HISTORY", name="历史接收加盟商")
        lead = Lead(
            source_type=LeadSourceKind.PLATFORM_MANUAL.value,
            source_kind=LeadSourceKind.PLATFORM_MANUAL.value,
            submitter_user_id=operation.id,
            customer_name="二次派发状态客户",
            phone_encrypted=encrypt_text("13900139730"),
            phone_hash=hash_phone("13900139730"),
            phone_fingerprint=fingerprint_phone("13900139730"),
            consent_confirmed=True,
            city="上海市",
            district="浦东新区",
            region_code="310115",
            source_channel="OTHER",
            source_detail="第2条回归",
            status=LeadV12Status.FOLLOWING.value,
            review_status="APPROVED",
            duplicate_status="CLEAR",
            current_follow_status="INTERESTED",
            imported_at=now,
        )
        db.add_all([historical_company, lead])
        db.flush()
        historical = Assignment(
            lead_id=lead.id,
            company_id=historical_company.id,
            receiver_company_id=historical_company.id,
            status=AssignmentStatus.RELEASED.value,
            points_price=100,
            lead_snapshot={},
            assigned_by=operation.id,
            assigned_at=now - timedelta(days=1),
            idempotency_key="item2-historical-assignment",
        )
        current = Assignment(
            lead_id=lead.id,
            company_id=current_company.id,
            receiver_company_id=current_company.id,
            status=AssignmentStatus.FOLLOWING.value,
            points_price=100,
            lead_snapshot={},
            assigned_by=operation.id,
            assigned_at=now,
            idempotency_key="item2-current-assignment",
        )
        db.add_all([historical, current])
        db.flush()
        lead.current_assignment_id = current.id
        db.add_all(
            [
                FollowUp(
                    assignment_id=historical.id,
                    company_id=historical_company.id,
                    status="NOT_INTERESTED",
                    note="历史加盟商跟进结果",
                    created_by=operation.id,
                    created_at=now - timedelta(hours=12),
                ),
                FollowUp(
                    assignment_id=current.id,
                    company_id=current_company.id,
                    status="INTERESTED",
                    note="当前加盟商跟进结果",
                    created_by=operation.id,
                    created_at=now,
                ),
            ]
        )
        db.commit()
        historical_company_id = historical_company.id

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation123!"},
    )
    assert login.status_code == 200, login.text
    response = client.get(
        f"/api/v1/v1.2/companies/{historical_company_id}/assignments"
    )
    assert response.status_code == 200, response.text
    [item] = response.json()["data"]["items"]
    assert item["current_follow_status"] == "NOT_INTERESTED"


def test_item_5_every_lead_source_has_the_same_correction_entry() -> None:
    source = ADMIN_WORKBENCH.read_text(encoding="utf-8")
    review = _function_slice(source, "async function review()", "function leadDetailBody")

    assert "data-lead-correction" in review
    assert "data-lead-correction-source" in review
    assert "data-lead-correction-recheck" in review
    assert "data-lead-correction-release" in review
    assert "/v1.2/admin/leads/" in review
    assert "更正客资" in source
    assert "['FEISHU_LEGACY','飞书历史导入']" in review
    assert "FEISHU_LEGACY:'飞书历史导入'" in source
    assert "preserveOriginalRegion" in source
    assert "regionChanged" in source


def test_item_8_lead_report_and_export_expose_every_requested_filter() -> None:
    source = ADMIN_WORKBENCH.read_text(encoding="utf-8")
    review = _function_slice(source, "async function review()", "function leadDetailBody")

    assert "/v1.2/reports/leads/filter-options" in review
    assert "/v1.2/reports/leads/search" in review
    assert 'id="lead-submitter-filter"' in review
    assert 'id="lead-phone-filter"' in review
    assert 'id="lead-region-filter"' in review
    assert 'id="lead-receiver-filter"' in review
    assert "submitter_user_id" in source
    assert "phone" in source
    assert "region" in source
    assert "receiver_company_id" in source
    assert "leadSubmitterId" in source
    assert "leadPhone" in source
    assert "leadRegion" in source
    assert "leadReceiverCompanyId" in source


def test_item_9_processed_history_has_independent_date_filter() -> None:
    source = ADMIN_WORKBENCH.read_text(encoding="utf-8")
    overview = _function_slice(source, "async function overview()", "const leadDateBoundary")

    assert "processedCreatedFrom" in source
    assert "processedCreatedTo" in source
    assert 'id="processed-created-from"' in overview
    assert 'id="processed-created-to"' in overview
    assert "created_from" in overview
    assert "created_to" in overview
    assert "processedPage=1" in overview
    assert "const processedDateEnd=value=>leadDateBoundary(value,true)" in source


def test_item_9_processed_range_is_half_open_and_excludes_correction_open(
    api_client,
) -> None:
    client, factory = api_client
    created_from = datetime(2026, 8, 29, 16, 0, tzinfo=timezone.utc)
    created_to = created_from + timedelta(days=1)
    with factory() as db:
        operation = db.scalar(select(User).where(User.username == "operation"))
        assert operation is not None
        db.add_all(
            [
                AuditLog(
                    request_id="item-9-boundary-inside",
                    actor_user_id=operation.id,
                    actor_role_codes=["OPERATION"],
                    action="V12_MANUAL_DISPATCH",
                    resource_type="assignment",
                    resource_id="item-9-boundary-inside",
                    metadata_json={},
                    created_at=created_to - timedelta(microseconds=1),
                ),
                AuditLog(
                    request_id="item-9-boundary-next-day",
                    actor_user_id=operation.id,
                    actor_role_codes=["OPERATION"],
                    action="V12_MANUAL_DISPATCH",
                    resource_type="assignment",
                    resource_id="item-9-boundary-next-day",
                    metadata_json={},
                    created_at=created_to,
                ),
                AuditLog(
                    request_id="item-9-correction-open",
                    actor_user_id=operation.id,
                    actor_role_codes=["OPERATION"],
                    action="V12_PLATFORM_LEAD_CORRECTION_OPEN",
                    resource_type="lead",
                    resource_id="item-9-correction-open",
                    metadata_json={},
                    created_at=created_from + timedelta(hours=1),
                ),
            ]
        )
        db.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation123!"},
    )
    assert login.status_code == 200, login.text
    response = client.get(
        "/api/v1/v1.2/operations/my-processed",
        params={
            "created_from": created_from.isoformat(),
            "created_to": created_to.isoformat(),
            "page_size": 100,
        },
    )
    assert response.status_code == 200, response.text
    resource_ids = {item["resource_id"] for item in response.json()["data"]["items"]}
    assert "item-9-boundary-inside" in resource_ids
    assert "item-9-boundary-next-day" not in resource_ids
    assert "item-9-correction-open" not in resource_ids


def test_item_9_server_request_ids_are_unique_when_client_reuses_header(
    api_client,
) -> None:
    client, _factory = api_client
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation123!"},
    )
    assert login.status_code == 200, login.text
    headers = {"x-request-id": "client-reused-correlation"}
    first = client.get("/api/v1/v1.2/reports/overview", headers=headers)
    second = client.get("/api/v1/v1.2/reports/overview", headers=headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    assert first.headers["x-request-id"] != headers["x-request-id"]
