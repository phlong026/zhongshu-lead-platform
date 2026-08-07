from __future__ import annotations

import pytest

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Company, Region, User
from apps.api.src.services.company_profile_v12 import (
    replace_service_areas,
    request_capability,
    review_capability,
)


def _identity(db, code: str) -> tuple[Company, User]:
    company = Company(code=code, name=f"测试公司-{code}", status="ACTIVE")
    db.add(company)
    db.flush()
    user = User(display_name="审核员", status="ACTIVE", company_id=company.id)
    db.add(user)
    db.flush()
    return company, user


def test_disabled_approved_capability_can_be_resubmitted(db) -> None:
    company, user = _identity(db, "REAPPLY001")
    item = request_capability(db, company.id, "LEAD_RECEIVER")
    review_capability(
        db,
        company_id=company.id,
        capability_code="LEAD_RECEIVER",
        approve=True,
        reviewed_by=user.id,
    )
    item.active = False
    db.flush()

    resubmitted = request_capability(db, company.id, "LEAD_RECEIVER")
    assert resubmitted.id == item.id
    assert resubmitted.review_status == "PENDING"
    assert resubmitted.active is False
    assert resubmitted.reviewed_by is None


def test_primary_service_area_must_be_city(db) -> None:
    db.add_all(
        [
            Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True),
            Region(code="420106", name="武昌区", level="DISTRICT", parent_code="420100", aliases=[], active=True),
        ]
    )
    company, _ = _identity(db, "AREA003")
    with pytest.raises(AppError) as exc_info:
        replace_service_areas(
            db,
            company_id=company.id,
            region_codes=["420106"],
            primary_city_code="420106",
        )
    assert exc_info.value.code == "PRIMARY_CITY_LEVEL_INVALID"


def test_service_district_must_belong_to_primary_city(db) -> None:
    db.add_all(
        [
            Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True),
            Region(code="430100", name="长沙市", level="CITY", aliases=[], active=True),
            Region(code="430102", name="芙蓉区", level="DISTRICT", parent_code="430100", aliases=[], active=True),
        ]
    )
    company, _ = _identity(db, "AREA004")
    with pytest.raises(AppError) as exc_info:
        replace_service_areas(
            db,
            company_id=company.id,
            region_codes=["420100", "430102"],
            primary_city_code="420100",
        )
    assert exc_info.value.code == "SERVICE_AREA_HIERARCHY_INVALID"
