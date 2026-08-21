from sqlalchemy import select

from apps.api.src.core.models import Company, PointsAccount
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.invite_binding_service import (
    bind_wechat_with_confirmation,
    create_company_invite,
    create_confirmation_intent,
)


def test_company_invite_confirmation_and_wechat_binding(db) -> None:
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
    account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company.id))
    assert account is not None
    assert account.balance == 0

    created = create_company_invite(db, company.id, None, 24)
    started = create_confirmation_intent(db, created.raw_token, "/h5/#/home")
    user, _, consumed_invite = bind_wechat_with_confirmation(
        db,
        started.confirmation_intent,
        openid="openid-1",
        nickname="张老板",
    )
    db.commit()

    assert consumed_invite.id == created.invite.id
    assert consumed_invite.used_at is not None
    assert user.company_id == company.id
    assert {role.code for role in user.roles} == {"FRANCHISE_OWNER"}
    assert db.get(Company, company.id).primary_user_id == user.id
