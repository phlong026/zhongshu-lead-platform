from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import (
    AuditLog,
    Company,
    CompanyCapability,
    CompanyServiceRegion,
    PointsAccount,
    Region,
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


def test_simple_company_creation_creates_pending_v12_dispatch_profile(api_client) -> None:
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
        "receiver_capability": "PENDING_REVIEW",
        "service_areas": "PENDING_REVIEW",
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
        assert legacy_regions == set()

        legacy_capabilities = set(
            db.scalars(
                select(CompanyCapability.category_code).where(
                    CompanyCapability.company_id == company.id,
                    CompanyCapability.active.is_(True),
                )
            ).all()
        )
        assert legacy_capabilities == set()

        receiver = db.scalar(
            select(CompanyLeadCapability).where(
                CompanyLeadCapability.company_id == company.id,
                CompanyLeadCapability.capability_code == "LEAD_RECEIVER",
            )
        )
        assert receiver is not None
        assert receiver.active is False
        assert receiver.review_status == "PENDING"

        service_areas = db.scalars(
            select(CompanyServiceAreaV12).where(
                CompanyServiceAreaV12.company_id == company.id
            )
        ).all()
        assert {"310000", "310104", "310115"}.issubset({item.region_code for item in service_areas})
        assert len(service_areas) > 10
        assert all(not item.active and item.review_status == "PENDING" for item in service_areas)
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


def test_simple_company_creation_materializes_selected_nationwide_regions(api_client) -> None:
    client, factory = api_client
    admin = _login_admin(client)

    response = client.post(
        "/api/v1/companies/simple",
        headers=admin,
        json={
            "name": "广州测试加盟商",
            "primary_city_code": "440100",
            "district_codes": ["440106"],
            "serve_all_districts": False,
        },
    )
    assert response.status_code == 200, response.text
    company_id = response.json()["data"]["id"]

    with factory() as db:
        city = db.get(Region, "440100")
        district = db.get(Region, "440106")
        assert city is not None
        assert (city.name, city.level, city.parent_code) == ("广州市", "CITY", None)
        assert district is not None
        assert (district.name, district.level, district.parent_code) == (
            "天河区",
            "DISTRICT",
            "440100",
        )
        assert not db.scalars(
            select(CompanyServiceRegion.region_code).where(
                CompanyServiceRegion.company_id == company_id,
                CompanyServiceRegion.active.is_(True),
            )
        ).all()
        service_areas = db.scalars(
            select(CompanyServiceAreaV12).where(CompanyServiceAreaV12.company_id == company_id)
        ).all()
        assert {item.region_code for item in service_areas} == {"440100", "440106"}
        assert all(not item.active and item.review_status == "PENDING" for item in service_areas)


def test_simple_company_creation_materializes_all_city_districts(api_client) -> None:
    client, factory = api_client
    admin = _login_admin(client)

    response = client.post(
        "/api/v1/companies/simple",
        headers=admin,
        json={
            "name": "广州全城加盟商",
            "primary_city_code": "440100",
            "district_codes": [],
            "serve_all_districts": True,
        },
    )
    assert response.status_code == 200, response.text
    company_id = response.json()["data"]["id"]

    with factory() as db:
        service_codes = set(
            db.scalars(
                select(CompanyServiceAreaV12.region_code).where(
                    CompanyServiceAreaV12.company_id == company_id,
                    CompanyServiceAreaV12.active.is_(False),
                    CompanyServiceAreaV12.review_status == "PENDING",
                )
            ).all()
        )
        assert {"440100", "440103", "440106"}.issubset(service_codes)
        assert len(service_codes) > 10
