from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from apps.api.src.core.models import (
    AuditLog,
    Company,
    CompanyCapability,
    CompanyServiceRegion,
    Lead,
    Notification,
    NotificationOutbox,
    Region,
    User,
)
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
    with factory() as db:
        legacy_receiver_categories = {
            item.category_code
            for item in db.scalars(
                select(CompanyCapability).where(
                    CompanyCapability.company_id == company.id,
                    CompanyCapability.brand_code.is_(None),
                    CompanyCapability.active.is_(True),
                )
            ).all()
        }
        assert {"OLD_RENOVATION", "SELF_BUILD", "INTERIOR"}.issubset(
            legacy_receiver_categories
        )

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
    with factory() as db:
        db.add(
            Region(
                code="320100",
                name="南京市",
                level="CITY",
                aliases=["南京", "南京市"],
                active=True,
            )
        )
        db.commit()
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
    missing_area_reason = client.post(
        f"/api/v1/v1.2/admin/service-areas/{areas[0]['id']}/review",
        headers=admin,
        json={"decision": "REJECT"},
    )
    assert missing_area_reason.status_code == 422
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
    with factory() as db:
        legacy_regions = {
            item.region_code: item.active
            for item in db.scalars(
                select(CompanyServiceRegion).where(
                    CompanyServiceRegion.company_id == company.id
                )
            ).all()
        }
        assert legacy_regions["310000"] is True
        assert legacy_regions["310115"] is True

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
    after_district_removal = _candidate(client, operation, lead_id, company.id)
    assert after_district_removal["eligible"] is True
    with factory() as db:
        removal_notice = db.scalar(
            select(Notification).where(
                Notification.company_id == company.id,
                Notification.title == "服务区域移除已通过",
            )
        )
        assert removal_notice is not None

    city_removal = _data(
        client.put(
            "/api/v1/v1.2/company/service-areas",
            headers=franchise,
            json={"region_codes": ["320100"], "primary_city_code": "320100"},
        )
    )
    shanghai = next(item for item in city_removal if item["region_code"] == "310000")
    assert shanghai["review_status"] == "PENDING"
    assert shanghai["active"] is True
    assert _candidate(client, operation, lead_id, company.id)["eligible"] is True

    removed_city = _data(
        client.post(
            f"/api/v1/v1.2/admin/service-areas/{shanghai['id']}/review",
            headers=admin,
            json={"decision": "APPROVE", "note": "同意停止上海市服务"},
        )
    )
    assert removed_city["active"] is False
    after_city_removal = _candidate(client, operation, lead_id, company.id)
    assert after_city_removal["eligible"] is False
    assert "SERVICE_REGION_MISMATCH" in after_city_removal["exclusion_reasons"]

    with factory() as db:
        legacy_district = db.scalar(
            select(CompanyServiceRegion).where(
                CompanyServiceRegion.company_id == company.id,
                CompanyServiceRegion.region_code == "310115",
            )
        )
        assert legacy_district is not None
        assert legacy_district.active is False
        legacy_city = db.scalar(
            select(CompanyServiceRegion).where(
                CompanyServiceRegion.company_id == company.id,
                CompanyServiceRegion.region_code == "310000",
            )
        )
        assert legacy_city is not None
        assert legacy_city.active is False
        assert db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.company_id == company.id,
                AuditLog.action == "V12_COMPANY_SERVICE_AREA_REVIEW",
            )
        ) == 4


def test_bulk_profile_approval_activates_pending_opening_items_but_not_removals(
    api_client,
) -> None:
    client, factory = api_client
    company = _company(factory)
    franchise = _login(client, "franchise_demo", "Franchise123!")
    operation = _login(client, "operation", "Operation123!")
    admin = _login(client, "admin", "Admin123!")
    _, areas = _request_profile(client, franchise)
    lead_id = _ready_lead(factory, "13900139812")

    approved = _data(
        client.post(
            f"/api/v1/v1.2/admin/companies/{company.id}/profile/approve-pending",
            headers=admin,
            json={"note": "加盟商开通资料已一次核验"},
        )
    )
    assert {item["capability_code"] for item in approved["capabilities"]} == {
        "LEAD_SUPPLIER",
        "LEAD_RECEIVER",
    }
    assert {item["region_code"] for item in approved["service_areas"]} == {
        item["region_code"] for item in areas
    }
    assert all(item["active"] for item in approved["capabilities"])
    assert all(item["active"] for item in approved["service_areas"])
    assert _candidate(client, operation, lead_id, company.id)["eligible"] is True

    removal = _data(
        client.put(
            "/api/v1/v1.2/company/service-areas",
            headers=franchise,
            json={"region_codes": ["310000"], "primary_city_code": "310000"},
        )
    )
    pending_removal = next(item for item in removal if item["region_code"] == "310115")
    no_opening_items = client.post(
        f"/api/v1/v1.2/admin/companies/{company.id}/profile/approve-pending",
        headers=admin,
        json={"note": "不应自动通过停用申请"},
    )
    assert no_opening_items.status_code == 409
    assert no_opening_items.json()["code"] == "COMPANY_PROFILE_NOT_PENDING"

    with factory() as db:
        area = db.get(CompanyServiceAreaV12, pending_removal["id"])
        assert area is not None
        assert area.active is True
        assert area.review_status == "PENDING"
        assert area.review_note.startswith("[REMOVE_REQUEST]")
        bulk_audits = db.scalars(
            select(AuditLog).where(
                AuditLog.company_id == company.id,
                AuditLog.action == "V12_COMPANY_PROFILE_BULK_APPROVE",
            )
        ).all()
        assert len(bulk_audits) == 1
        notifications = db.scalars(
            select(Notification).where(
                Notification.company_id == company.id,
                Notification.scene == "V12_COMPANY_PROFILE_APPROVED",
            )
        ).all()
        outboxes = db.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == company.id,
                NotificationOutbox.event_type == "V12_COMPANY_PROFILE_APPROVED",
            )
        ).all()
        assert len(notifications) == 1
        assert len(outboxes) == 1


def test_rejected_service_area_removal_notifies_owner_with_removal_result(api_client) -> None:
    client, factory = api_client
    company = _company(factory)
    franchise = _login(client, "franchise_demo", "Franchise123!")
    admin = _login(client, "admin", "Admin123!")
    _request_profile(client, franchise)
    _data(
        client.post(
            f"/api/v1/v1.2/admin/companies/{company.id}/profile/approve-pending",
            headers=admin,
            json={"note": "开通资料已核验"},
        )
    )

    removal = _data(
        client.put(
            "/api/v1/v1.2/company/service-areas",
            headers=franchise,
            json={"region_codes": ["310000"], "primary_city_code": "310000"},
        )
    )
    district = next(item for item in removal if item["region_code"] == "310115")
    restored = _data(
        client.post(
            f"/api/v1/v1.2/admin/service-areas/{district['id']}/review",
            headers=admin,
            json={"decision": "REJECT", "note": "保留浦东新区服务"},
        )
    )
    assert restored["active"] is True
    with factory() as db:
        removal_notice = db.scalar(
            select(Notification).where(
                Notification.company_id == company.id,
                Notification.title == "服务区域移除未通过",
            )
        )
        assert removal_notice is not None


def test_company_profile_endpoints_enforce_role_and_company_boundaries(api_client) -> None:
    client, factory = api_client
    franchise = _login(client, "franchise_demo", "Franchise123!")
    telesales = _login(client, "telesales", "Telesales123!")

    _request_profile(client, franchise)

    admin_queue = client.get(
        "/api/v1/v1.2/admin/company-capabilities",
        headers=franchise,
    )
    unauthorized_request = client.post(
        "/api/v1/v1.2/company/capabilities",
        headers=telesales,
        json={"capability_code": "LEAD_RECEIVER"},
    )
    assert admin_queue.status_code == 403
    assert unauthorized_request.status_code == 403

    with factory() as db:
        assert db.scalar(select(func.count(CompanyLeadCapability.id))) == 2
        assert db.scalar(select(func.count(CompanyServiceAreaV12.id))) == 2

def test_legacy_company_capability_and_area_review_routes_are_deprecated(api_client) -> None:
    client, _factory = api_client
    paths = client.get("/openapi.json").json()["paths"]

    legacy_operations = (
        ("/api/v1/v1.2/company/capabilities", "post"),
        ("/api/v1/v1.2/company/service-areas", "put"),
        ("/api/v1/v1.2/admin/company-capabilities", "get"),
        (
            "/api/v1/v1.2/admin/companies/{company_id}/capabilities/{capability_code}/review",
            "post",
        ),
        ("/api/v1/v1.2/admin/service-areas", "get"),
        ("/api/v1/v1.2/admin/service-areas/{area_id}/review", "post"),
    )
    for path, method in legacy_operations:
        assert paths[path][method]["deprecated"] is True

    assert "deprecated" not in paths["/api/v1/v1.2/company/capabilities"]["get"]
    assert "deprecated" not in paths["/api/v1/v1.2/company/service-areas"]["get"]
    current = paths[
        "/api/v1/v1.2/admin/companies/{company_id}/capabilities/{capability_code}"
    ]["put"]
    assert "deprecated" not in current
