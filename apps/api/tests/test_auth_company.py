from sqlalchemy import select

from apps.api.src.core.models import Company, PointsAccount
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.auth_service import bind_wechat_by_invite, create_company_invite
from apps.api.src.services.company_service import create_company


def test_company_invite_and_wechat_binding(db) -> None:
    company = create_company(
        db,
        CompanyCreateBody(
            code="SH001",
            name="上海测试加盟商",
            owner_name="张老板",
            region_codes=["310100"],
            capabilities=[{"category_code": "OLD_RENOVATION", "brand_code": None}],
        ),
    )
    db.commit()
    assert db.scalar(select(PointsAccount).where(PointsAccount.company_id == company.id)).balance == 0

    _, token = create_company_invite(db, company.id, None, 24)
    user, _ = bind_wechat_by_invite(db, token, "openid-1", "张老板")
    db.commit()
    assert user.company_id == company.id
    assert {role.code for role in user.roles} == {"FRANCHISE_OWNER"}
    assert db.get(Company, company.id).primary_user_id == user.id
