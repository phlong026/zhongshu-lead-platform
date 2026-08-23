from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import (
    AuditLog,
    Company,
    CompanyCapability,
    CompanyServiceRegion,
    PointsAccount,
)
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12


def _login_admin(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin123!"},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def test_simple_company_creation_links_legacy_and_v12_dispatch_profiles(api_client) -> None:
    client, factory = api_client
    admin = _login_admin(client)

    response = client.post(
        "/api/v1/companies/simple",
        headers=admin,
        json={
            "name": "浦江测试加盟商",
            "owner_name": "陈经理",
            "contact_phone": "13800138000",
            "primary_city_code": "310000",
            "district_codes": [],
            "serve_all_districts": True,
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["code"].startswith("JM-")
    assert result["readiness"] == {
        "points_account": "READY",
        "receiver_capability": "APPROVED",
        "service_areas": "APPROVED",
    }

    with factory() as db:
        company = db.get(Company, result["id"])
        assert company is not None
        assert db.scalar(select(PointsAccount).where(PointsAccount.company_id == company.id))

        legacy_regions = set(
            db.scalars(
                select(CompanyServiceRegion.region_code).where(
                    CompanyServiceRegion.company_id == company.id,
                    CompanyServiceRegion.active.is_(True),
                )
            ).all()
        )
        assert legacy_regions == {"310000", "310104", "310115"}

        legacy_capabilities = set(
            db.scalars(
                select(CompanyCapability.category_code).where(
                    CompanyCapability.company_id == company.id,
                    CompanyCapability.active.is_(True),
                )
            ).all()
        )
        assert {"OLD_RENOVATION", "SELF_BUILD", "INTERIOR"}.issubset(
            legacy_capabilities
        )

        receiver = db.scalar(
            select(CompanyLeadCapability).where(
                CompanyLeadCapability.company_id == company.id,
                CompanyLeadCapability.capability_code == "LEAD_RECEIVER",
            )
        )
        assert receiver is not None
        assert receiver.active is True
        assert receiver.review_status == "APPROVED"

        service_areas = db.scalars(
            select(CompanyServiceAreaV12).where(
                CompanyServiceAreaV12.company_id == company.id
            )
        ).all()
        assert {item.region_code for item in service_areas} == legacy_regions
        assert all(item.active and item.review_status == "APPROVED" for item in service_areas)
        assert next(item for item in service_areas if item.region_code == "310000").is_primary_city

        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "COMPANY_SIMPLE_CREATE",
                AuditLog.resource_id == company.id,
            )
        )
        assert audit is not None


def test_simple_company_creation_rejects_region_outside_primary_city(api_client) -> None:
    client, _ = api_client
    admin = _login_admin(client)

    response = client.post(
        "/api/v1/companies/simple",
        headers=admin,
        json={
            "name": "错误地区加盟商",
            "primary_city_code": "310000",
            "district_codes": ["320500"],
            "serve_all_districts": False,
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SERVICE_AREA_HIERARCHY_INVALID"
