from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from apps.api.src.core.models import AuditLog, Company, Lead, User
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_phone
from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def _data(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == "OK"
    return payload["data"]


def _company(factory) -> Company:
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        assert company is not None
        db.expunge(company)
        return company


def _request_profile(client, franchise: dict[str, str]) -> tuple[list[dict], list[dict]]:
    capabilities = [
        _data(
            client.post(
                "/api/v1/v1.2/company/capabilities",
                headers=franchise,
                json={"capability_code": code},
            )
        )
        for code in ("LEAD_SUPPLIER", "LEAD_RECEIVER")
    ]
    areas = _data(
        client.put(
            "/api/v1/v1.2/company/service-areas",
            headers=franchise,
            json={
                "region_codes": ["310000", "310115"],
                "primary_city_code": "310000",
            },
        )
    )
    return capabilities, areas


def _ready_lead(factory, phone: str = "13900139801") -> str:
    with factory() as db:
        operation = db.scalar(select(User).where(User.username == "operation"))
        assert operation is not None
        lead = Lead(
            source_type=LeadSourceKind.PLATFORM_MANUAL.value,
            source_kind=LeadSourceKind.PLATFORM_MANUAL.value,
            submitter_user_id=operation.id,
            customer_name="公司档案候选验证客户",
            phone_encrypted=encrypt_text(phone),
            phone_hash=hash_phone(phone),
            phone_fingerprint=fingerprint_phone(phone),
            consent_confirmed=True,
            city="上海市",
            district="浦东新区",
            region_code="310115",
            category_code="OLD_RENOVATION",
            brand_code="ZHONGSHU",
            need_summary="验证能力和服务区域审核前后候选变化",
            status=LeadV12Status.READY_DISPATCH.value,
            review_status="APPROVED",
            duplicate_status="CLEAR",
            imported_at=datetime.now(timezone.utc),
            submitted_at=datetime.now(timezone.utc),
            raw_payload={},
        )
        db.add(lead)
        db.commit()
        return lead.id


def _candidate(client, operation: dict[str, str], lead_id: str, company_id: str) -> dict:
    payload = _data(
        client.get(
            f"/api/v1/v1.2/dispatch-pool/{lead_id}/candidates",
            headers=operation,
        )
    )
    return next(item for item in payload["candidates"] if item["company_id"] == company_id)


def test_capability_review_persists_reason_and_keeps_supplier_receiver_independent(
    api_client,
) -> None:
    client, factory = api_client
    company = _company(factory)
    franchise = _login(client, "franchise_demo", "Franchise123!")
    admin = _login(client, "admin", "Admin123!")

    capabilities, _ = _request_profile(client, franchise)
    receiver = next(item for item in capabilities if item["capability_code"] == "LEAD_RECEIVER")
    replay = _data(
        client.post(
            "/api/v1/v1.2/company/capabilities",
            headers=franchise,
            json={"capability_code": "LEAD_RECEIVER"},
        )
    )
    assert replay["id"] == receiver["id"]

    queue = _data(
        client.get(
            "/api/v1/v1.2/admin/company-capabilities?review_status=PENDING&page=1&page_size=20",
            headers=admin,
        )
    )
    assert queue["total"] == 2
    assert {item["company_id"] for item in queue["items"]} == {company.id}
    assert {item["company_name"] for item in queue["items"]} == {company.name}
    assert {item["company_code"] for item in queue["items"]} == {company.code}

    missing_reason = client.post(
        f"/api/v1/v1.2/admin/companies/{company.id}/capabilities/LEAD_SUPPLIER/review",
        headers=admin,
        json={"decision": "REJECT"},
    )
    assert missing_reason.status_code == 422

    supplier = _data(
        client.post(
            f"/api/v1/v1.2/admin/companies/{company.id}/capabilities/LEAD_SUPPLIER/review",
            headers=admin,
            json={"decision": "REJECT", "note": "供应材料尚未完成平台备案"},
        )
    )
    receiver = _data(
        client.post(
            f"/api/v1/v1.2/admin/companies/{company.id}/capabilities/LEAD_RECEIVER/review",
            headers=admin,
            json={"decision": "APPROVE", "note": "接收团队与服务承诺已核验"},
        )
    )
    assert supplier["active"] is False
    assert supplier["review_status"] == "REJECTED"
    assert supplier["review_note"] == "供应材料尚未完成平台备案"
    assert receiver["active"] is True
    assert receiver["review_status"] == "APPROVED"
    assert receiver["review_note"] == "接收团队与服务承诺已核验"

    own = _data(
        client.get("/api/v1/v1.2/company/capabilities", headers=franchise)
    )
    assert {
        item["capability_code"]: (item["active"], item["review_note"])
        for item in own
    } == {
        "LEAD_RECEIVER": (True, "接收团队与服务承诺已核验"),
        "LEAD_SUPPLIER": (False, "供应材料尚未完成平台备案"),
    }


def test_service_area_approval_and_removal_change_dispatch_eligibility_only_after_review(
    api_client,
) -> None:
    client, factory = api_client
    company = _company(factory)
    franchise = _login(client, "franchise_demo", "Franchise123!")
    operation = _login(client, "operation", "Operation123!")
    admin = _login(client, "admin", "Admin123!")
    capabilities, areas = _request_profile(client, franchise)
    lead_id = _ready_lead(factory)

    pending = _candidate(client, operation, lead_id, company.id)
    assert pending["eligible"] is False
    assert "RECEIVER_CAPABILITY_REQUIRED" in pending["exclusion_reasons"]
    assert "SERVICE_REGION_MISMATCH" in pending["exclusion_reasons"]

    _data(
        client.post(
            f"/api/v1/v1.2/admin/companies/{company.id}/capabilities/LEAD_RECEIVER/review",
            headers=admin,
            json={"decision": "APPROVE", "note": "接收能力审核通过"},
        )
    )
    for area in areas:
        approved = _data(
            client.post(
                f"/api/v1/v1.2/admin/service-areas/{area['id']}/review",
                headers=admin,
                json={"decision": "APPROVE", "note": "服务区域资料已核验"},
            )
        )
        assert approved["active"] is True
        assert approved["review_note"] == "服务区域资料已核验"

    approved_candidate = _candidate(client, operation, lead_id, company.id)
    assert approved_candidate["eligible"] is True

    removal = _data(
        client.put(
            "/api/v1/v1.2/company/service-areas",
            headers=franchise,
            json={"region_codes": ["310000"], "primary_city_code": "310000"},
        )
    )
    district = next(item for item in removal if item["region_code"] == "310115")
    assert district["review_status"] == "PENDING"
    assert district["active"] is True
    assert district["review_note"].startswith("[REMOVE_REQUEST]")
    assert _candidate(client, operation, lead_id, company.id)["eligible"] is True

    queue = _data(
        client.get(
            "/api/v1/v1.2/admin/service-areas?review_status=PENDING&page=1&page_size=20",
            headers=admin,
        )
    )
    pending_district = next(item for item in queue["items"] if item["id"] == district["id"])
    assert pending_district["company_name"] == company.name
    assert pending_district["company_code"] == company.code

    removed = _data(
        client.post(
            f"/api/v1/v1.2/admin/service-areas/{district['id']}/review",
            headers=admin,
            json={"decision": "APPROVE", "note": "同意停止浦东新区服务"},
        )
    )
    assert removed["active"] is False
    assert removed["review_note"] == "同意停止浦东新区服务"
    after_removal = _candidate(client, operation, lead_id, company.id)
    assert after_removal["eligible"] is False
    assert "SERVICE_REGION_MISMATCH" in after_removal["exclusion_reasons"]

    with factory() as db:
        assert db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.company_id == company.id,
                AuditLog.action == "V12_COMPANY_SERVICE_AREA_REVIEW",
            )
        ) == 3


def test_company_profile_endpoints_enforce_role_and_company_boundaries(api_client) -> None:
    client, factory = api_client
    franchise = _login(client, "franchise_demo", "Franchise123!")
    owner = _login(client, "owner", "Owner123!")

    _request_profile(client, franchise)

    admin_queue = client.get(
        "/api/v1/v1.2/admin/company-capabilities",
        headers=franchise,
    )
    unauthorized_request = client.post(
        "/api/v1/v1.2/company/capabilities",
        headers=owner,
        json={"capability_code": "LEAD_RECEIVER"},
    )
    assert admin_queue.status_code == 403
    assert unauthorized_request.status_code == 403

    with factory() as db:
        assert db.scalar(select(func.count(CompanyLeadCapability.id))) == 2
        assert db.scalar(select(func.count(CompanyServiceAreaV12.id))) == 2
