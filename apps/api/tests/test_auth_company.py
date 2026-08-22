from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Company, InviteToken, PointsAccount, User, WechatIdentity
from apps.api.src.core.security import hash_token
from apps.api.src.core.time import utcnow
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.auth_service import (
    bind_wechat_by_invite,
    build_invite_copy_text,
    create_company_invite,
    login_or_bind_wechat,
)
from apps.api.src.services.company_service import create_company


def _company_body(code: str, **overrides) -> CompanyCreateBody:
    payload = {
        "code": code,
        "name": "上海测试加盟商",
        "owner_name": "张老板",
        "region_codes": ["310100"],
        "capabilities": [{"category_code": "OLD_RENOVATION", "brand_code": None}],
    }
    payload.update(overrides)
    return CompanyCreateBody(**payload)


def _legacy_invite(db, company_id: str, label: str) -> InviteToken:
    """Directly insert an invite, simulating rows created before P0-06 uniqueness."""

    invite = InviteToken(
        token_hash=hash_token(label),
        company_id=company_id,
        expires_at=utcnow() + timedelta(hours=1),
    )
    db.add(invite)
    db.commit()
    return invite


def _admin_headers(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin123!"},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def test_company_invite_and_wechat_binding(db) -> None:
    company = create_company(db, _company_body("SH001"))
    db.commit()
    assert db.scalar(select(PointsAccount).where(PointsAccount.company_id == company.id)).balance == 0

    _, token, superseded = create_company_invite(db, company.id, None, 24)
    assert superseded == []
    user, _ = bind_wechat_by_invite(db, token, "openid-1", "张老板")
    db.commit()
    assert user.company_id == company.id
    assert {role.code for role in user.roles} == {"FRANCHISE_OWNER"}
    assert db.get(Company, company.id).primary_user_id == user.id


def test_invite_copy_text_carries_recipient_and_company(db) -> None:
    company = create_company(db, _company_body("SH-COPY", owner_name="李负责人"))
    invite, raw, _ = create_company_invite(db, company.id, None, 24)
    url = f"http://localhost:8000/h5/#/login?invite={raw}"
    text = build_invite_copy_text(company.owner_name, company.name, url, invite.expires_at.isoformat())
    assert text.startswith("李负责人，您好：这是【上海测试加盟商】的微信绑定邀请，请在微信内打开：")
    assert url in text
    assert invite.expires_at.isoformat() in text


def test_invite_copy_text_falls_back_without_owner_name(db) -> None:
    company = create_company(db, _company_body("SH-NOOWNER", owner_name=None))
    invite, raw, _ = create_company_invite(db, company.id, None, 24)
    text = build_invite_copy_text(company.owner_name, company.name, f"http://localhost:8000/h5/#/login?invite={raw}", invite.expires_at.isoformat())
    assert text.startswith("您好：这是【上海测试加盟商】的微信绑定邀请，请在微信内打开：")


def test_invite_http_response_carries_safe_recipient_info(api_client) -> None:
    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        company = create_company(db, _company_body("SH-HTTPINV", owner_name="王老板"))
        db.commit()
        company_id = company.id
    response = client.post(
        f"/api/v1/auth/companies/{company_id}/invites",
        headers=headers,
        json={"expires_hours": 72},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["company_name"] == "上海测试加盟商"
    assert data["owner_name"] == "王老板"
    assert data["copy_text"].startswith("王老板，您好：这是【上海测试加盟商】的微信绑定邀请，请在微信内打开：")
    assert data["url"] in data["copy_text"]
    assert data["expires_at"] in data["copy_text"]
    # URL 只携带 token，不拼入姓名或公司明文
    assert "invite=" in data["url"]
    assert "王老板" not in data["url"]
    assert "上海测试加盟商" not in data["url"]
    assert "contact_phone" not in data
    assert "phone" not in data["copy_text"]


def test_invite_http_response_omits_missing_owner_as_null(api_client) -> None:
    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        company = create_company(db, _company_body("SH-HTTPNULL", owner_name=None))
        db.commit()
        company_id = company.id
    response = client.post(
        f"/api/v1/auth/companies/{company_id}/invites",
        headers=headers,
        json={"expires_hours": 72},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["owner_name"] is None
    assert data["copy_text"].startswith("您好：这是【上海测试加盟商】的微信绑定邀请，请在微信内打开：")


def test_pending_company_cannot_create_invite(db) -> None:
    company = create_company(db, _company_body("SH-PENDING"))
    company.status = "PENDING"
    db.commit()
    with pytest.raises(AppError) as exc:
        create_company_invite(db, company.id, None, 24)
    assert exc.value.code == "AUTH_COMPANY_DISABLED"
    assert exc.value.status_code == 403


def test_bound_company_rejects_new_invite_creation(db) -> None:
    company = create_company(db, _company_body("SH-BOUND"))
    _, raw, _ = create_company_invite(db, company.id, None, 24)
    bind_wechat_by_invite(db, raw, "openid-bound", "张老板")
    db.commit()
    with pytest.raises(AppError) as exc:
        create_company_invite(db, company.id, None, 24)
    assert exc.value.code == "AUTH_COMPANY_ALREADY_BOUND"


def test_second_invite_supersedes_previous_valid_invite(db) -> None:
    company = create_company(db, _company_body("SH-SUPERSEDE"))
    first, first_raw, first_superseded = create_company_invite(db, company.id, None, 24)
    assert first_superseded == []
    db.commit()
    second, second_raw, superseded = create_company_invite(db, company.id, None, 24)
    db.commit()
    assert superseded == [first.id]
    assert second.id != first.id
    refreshed_first = db.get(InviteToken, first.id)
    assert refreshed_first.revoked_at is not None
    # 旧链接不能再完成绑定，错误统一为邀请失效，不泄露被哪条新邀请替换
    with pytest.raises(AppError) as exc:
        bind_wechat_by_invite(db, first_raw, "openid-superseded", "旧邀请")
    assert exc.value.code == "AUTH_INVITE_INVALID"
    db.rollback()
    # 新链接仍然有效
    user, _ = bind_wechat_by_invite(db, second_raw, "openid-fresh", "新负责人")
    db.commit()
    assert user.company_id == company.id


def test_superseded_invite_preview_fails(api_client) -> None:
    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        company = create_company(db, _company_body("SH-SUPER-PREVIEW"))
        db.commit()
        company_id = company.id
    first = client.post(f"/api/v1/auth/companies/{company_id}/invites", headers=headers, json={"expires_hours": 24}).json()["data"]
    second = client.post(f"/api/v1/auth/companies/{company_id}/invites", headers=headers, json={"expires_hours": 24}).json()["data"]
    assert second["revoked_invite_count"] == 1
    stale = client.get("/api/v1/auth/invites/preview", params={"invite": first["token"]})
    assert stale.status_code == 400
    assert stale.json()["code"] == "AUTH_INVITE_INVALID"
    fresh = client.get("/api/v1/auth/invites/preview", params={"invite": second["token"]})
    assert fresh.status_code == 200


def test_new_openid_cannot_silently_overwrite_primary_user(db) -> None:
    company = create_company(db, _company_body("SH-OVERWRITE"))
    _, raw, _ = create_company_invite(db, company.id, None, 24)
    first_user, _ = bind_wechat_by_invite(db, raw, "openid-owner", "原负责人")
    db.commit()
    legacy = _legacy_invite(db, company.id, "legacy-invite-raw-token-001")
    with pytest.raises(AppError) as exc:
        login_or_bind_wechat(db, openid="openid-attacker", nickname="冒名者", invite_token="legacy-invite-raw-token-001")
    assert exc.value.code == "AUTH_COMPANY_ALREADY_BOUND"
    db.rollback()
    assert db.get(Company, company.id).primary_user_id == first_user.id
    # M2：占用失败的事务不得残留第二个用户、角色或微信身份（隐式回滚依赖
    # core.database.get_db 的 session.close()，由本断言锁定）。
    assert db.scalar(select(func.count()).select_from(User).where(User.company_id == company.id)) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(WechatIdentity)
            .join(User, User.id == WechatIdentity.user_id)
            .where(User.company_id == company.id)
        )
        == 1
    )
    # 旧邀请未被失败事务消费
    assert db.get(InviteToken, legacy.id).used_at is None


def test_bound_wechat_login_with_same_company_invite_consumes_invite(db) -> None:
    company = create_company(db, _company_body("SH-RELOGIN"))
    _, raw, _ = create_company_invite(db, company.id, None, 24)
    user, _ = bind_wechat_by_invite(db, raw, "openid-relogin", "张老板")
    db.commit()
    second = _legacy_invite(db, company.id, "second-invite-raw-token-002")
    again, _ = login_or_bind_wechat(db, openid="openid-relogin", nickname="张老板", invite_token="second-invite-raw-token-002")
    db.commit()
    assert again.id == user.id
    assert db.get(InviteToken, second.id).used_at is not None
    assert db.get(Company, company.id).primary_user_id == user.id
