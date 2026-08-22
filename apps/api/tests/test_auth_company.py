from __future__ import annotations

from datetime import timedelta
from pathlib import Path

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
from apps.api.src.services.company_service import create_company, find_company_by_contact_phone


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



def test_list_company_invites_returns_full_lifecycle_records(api_client) -> None:
    """P1-01：邀请记录列表覆盖全部生命周期状态，创建人可追溯，不泄露 token。"""

    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        company = create_company(db, _company_body("SH-LIST"))
        db.commit()
        company_id = company.id
        # 记录1：被第二条邀请同事务自动撤销（REVOKED）
        client.post(f"/api/v1/auth/companies/{company_id}/invites", headers=headers, json={"expires_hours": 24})
        # 记录2：当前有效（ACTIVE），创建人为 admin
        active = client.post(
            f"/api/v1/auth/companies/{company_id}/invites", headers=headers, json={"expires_hours": 24}
        ).json()["data"]
        # 记录3：直接插入的过期行（EXPIRED），无创建人，用于验证「未记录」
        db.add(
            InviteToken(
                token_hash=hash_token("expired-list-token-0001"),
                company_id=company_id,
                expires_at=utcnow() - timedelta(hours=1),
            )
        )
        db.commit()

    response = client.get(f"/api/v1/auth/companies/{company_id}/invites", headers=headers)
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert len(items) == 3
    by_status = {item["status"]: item for item in items}
    assert set(by_status) == {"REVOKED", "ACTIVE", "EXPIRED"}
    assert by_status["REVOKED"]["revoked_at"] is not None
    assert by_status["ACTIVE"]["id"] == active["invite_id"]
    assert by_status["ACTIVE"]["expires_at"] == active["expires_at"]
    assert by_status["ACTIVE"]["created_by_name"]
    assert by_status["EXPIRED"]["created_by_name"] is None
    # 列表绝不携带 token 原文或哈希
    assert all("token" not in item and "token_hash" not in item for item in items)


def test_list_company_invites_shows_current_primary_account_for_used_invite(api_client) -> None:
    """P1-02：使用结果与当前主账号可追溯；无法证实的历史字段为「未记录」。"""

    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        bound = create_company(db, _company_body("SH-TRACE-BOUND"))
        _, raw, _ = create_company_invite(db, bound.id, None, 24)
        bind_wechat_by_invite(db, raw, "openid-trace", "张老板")
        db.commit()
        bound_id = bound.id
        # 模拟历史遗留：used_at 非空但公司从未绑定主账号
        legacy_used = create_company(db, _company_body("SH-TRACE-LEGACY"))
        db.add(
            InviteToken(
                token_hash=hash_token("legacy-used-token-0002"),
                company_id=legacy_used.id,
                expires_at=utcnow() + timedelta(hours=1),
                used_at=utcnow() - timedelta(hours=2),
            )
        )
        db.commit()
        legacy_id = legacy_used.id

    bound_items = client.get(f"/api/v1/auth/companies/{bound_id}/invites", headers=headers).json()["data"]["items"]
    used = next(item for item in bound_items if item["status"] == "USED")
    assert used["used_at"] is not None
    assert used["primary_account_name"] == "张老板"

    legacy_items = client.get(f"/api/v1/auth/companies/{legacy_id}/invites", headers=headers).json()["data"]["items"]
    legacy_used_item = legacy_items[0]
    assert legacy_used_item["status"] == "USED"
    assert legacy_used_item["primary_account_name"] is None


def test_revoke_invite_returns_404_for_missing_invite(api_client) -> None:
    """M4：撤销不存在的邀请必须明确失败，不再静默返回成功。"""

    client, _ = api_client
    headers = _admin_headers(client)
    response = client.post("/api/v1/auth/invites/not-a-real-invite-id/revoke", headers=headers)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "INVITE_NOT_FOUND"


def test_list_company_invites_requires_admin_permission(api_client) -> None:
    """邀请记录仅限后台运营查看，未认证请求不得获得数据。"""

    client, factory = api_client
    with factory() as db:
        company = create_company(db, _company_body("SH-LIST-PERM"))
        db.commit()
        company_id = company.id
    response = client.get(f"/api/v1/auth/companies/{company_id}/invites")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"

def test_revoke_invite_validates_lifecycle_status(api_client) -> None:
    """I8：已使用/已撤销/已过期的邀请撤销必须明确拒绝，且 revoked_at 不被盖写。"""

    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        company = create_company(db, _company_body("SH-REVOKE-LIFE"))
        db.flush()
        used = InviteToken(
            token_hash=hash_token("rev-used-01"),
            company_id=company.id,
            expires_at=utcnow() + timedelta(hours=1),
            used_at=utcnow() - timedelta(hours=1),
        )
        revoked = InviteToken(
            token_hash=hash_token("rev-revoked-01"),
            company_id=company.id,
            expires_at=utcnow() + timedelta(hours=1),
            revoked_at=utcnow() - timedelta(hours=1),
        )
        expired = InviteToken(
            token_hash=hash_token("rev-expired-01"),
            company_id=company.id,
            expires_at=utcnow() - timedelta(hours=1),
        )
        db.add_all([used, revoked, expired])
        db.commit()
        expectations = {
            "INVITE_ALREADY_USED": used.id,
            "INVITE_ALREADY_REVOKED": revoked.id,
            "INVITE_ALREADY_EXPIRED": expired.id,
        }

    for code, invite_id in expectations.items():
        response = client.post(f"/api/v1/auth/invites/{invite_id}/revoke", headers=headers)
        assert response.status_code == 409, response.text
        assert response.json()["code"] == code, response.text

    with factory() as db:
        used_row = db.get(InviteToken, expectations["INVITE_ALREADY_USED"])
        assert used_row is not None and used_row.revoked_at is None



def test_invite_records_keep_invitee_snapshot_after_company_rename(api_client) -> None:
    """P2-01：邀请对象快照在公司/负责人改名后保持发出时的值；存量行无快照。"""

    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        company = create_company(db, _company_body("SH-SNAPSHOT"))
        db.commit()
        created_id = client.post(
            f"/api/v1/auth/companies/{company.id}/invites", headers=headers, json={"expires_hours": 24}
        ).json()["data"]["invite_id"]
        # legacy 行未过期同为 ACTIVE，必须按 id 区分，不能按状态取第一条。
        legacy = _legacy_invite(db, company.id, "legacy-snapshot-token-0003")
        snapshot_name = company.name
        snapshot_owner = company.owner_name
        company.name = "改名后的公司"
        company.owner_name = "新负责人"
        db.commit()
        company_id = company.id
        legacy_id = legacy.id

    items = client.get(f"/api/v1/auth/companies/{company_id}/invites", headers=headers).json()["data"]["items"]
    assert len(items) == 2
    active = next(item for item in items if item["id"] == created_id)
    assert active["invitee_name"] == snapshot_owner == "张老板"
    assert active["company_name"] == snapshot_name == "上海测试加盟商"
    legacy_item = next(item for item in items if item["id"] == legacy_id)
    # 迁移前的存量邀请没有快照：返回 None 交由前端显示「未记录」，不回落当前值。
    assert legacy_item["invitee_name"] is None
    assert legacy_item["company_name"] is None


def test_invite_snapshot_migration_is_registered_on_alembic_chain() -> None:
    """P2-01：快照列迁移 0007 必须挂在当前链尾且包含两列，防漂移。"""

    migration = Path("migrations/versions/0007_invite_snapshot.py").read_text(encoding="utf-8")
    assert 'revision = "0007_invite_snapshot"' in migration
    assert 'down_revision = "0006_capability_review_note"' in migration
    assert "invitee_name_snapshot" in migration
    assert "company_name_snapshot" in migration


def test_find_company_by_contact_phone_matches_normalized_hash(db) -> None:
    """P2-02：规范化手机号经 HMAC 命中唯一 ACTIVE 公司；停用/异号码不命中。"""

    matched = create_company(db, _company_body("SH-PHONE-A", contact_phone="13900001111"))
    create_company(db, _company_body("SH-PHONE-B", contact_phone="13900002222"))
    disabled = create_company(db, _company_body("SH-PHONE-C", contact_phone="13900003333"))
    disabled.status = "DISABLED"
    db.commit()

    assert find_company_by_contact_phone(db, "+86 139 0000 1111").id == matched.id
    assert find_company_by_contact_phone(db, "13900001111").id == matched.id
    assert find_company_by_contact_phone(db, "13900009999") is None
    # 停用公司不是可绑定目标，不参与匹配。
    assert find_company_by_contact_phone(db, "13900003333") is None
    # 非 11 位输入直接拒绝，不做无意义查询。
    assert find_company_by_contact_phone(db, "12345") is None
