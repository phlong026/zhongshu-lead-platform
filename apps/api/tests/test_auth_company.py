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
    create_internal_user,
    login_or_bind_wechat,
    validate_invite,
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


def _expect_invite_invalid(fn) -> None:
    """N13：非法邀请的一切入口（validate/consume/bind）必须同码拒绝——
    raises+断言样板收敛到一处，不再逐处手抄。"""

    with pytest.raises(AppError) as exc:
        fn()
    assert exc.value.code == "AUTH_INVITE_INVALID"


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


@pytest.mark.parametrize("status", ["PENDING", "DISABLED"])
def test_non_active_company_cannot_create_invite(db, status) -> None:
    # I11：实现为 status != "ACTIVE" 一律拒绝；DISABLED 与 PENDING 同路径须都锁定
    # （Company.status 是自由字符串，非数据库枚举，两条路径都可能被回归改坏）。
    company = create_company(db, _company_body("SH-NOT-ACTIVE"))
    company.status = status
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
    _expect_invite_invalid(lambda: bind_wechat_by_invite(db, first_raw, "openid-superseded", "旧邀请"))
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
    """P1-02/N9：使用者是消费邀请时落库的 used_by_user_id——绑定流消费的
    邀请归因到真实使用者；无法核实的历史字段保持「未记录」。"""

    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        bound = create_company(db, _company_body("SH-TRACE-BOUND"))
        invite, raw, _ = create_company_invite(db, bound.id, None, 24)
        user, _ = bind_wechat_by_invite(db, raw, "openid-trace", "张老板")
        db.commit()
        db.refresh(invite)  # consume/update 走 synchronize_session=False，缓存对象不回填
        assert invite.used_by_user_id == user.id, "消费邀请必须同事务写回真实使用者"
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
    assert used["used_by_name"] == "张老板"

    legacy_items = client.get(f"/api/v1/auth/companies/{legacy_id}/invites", headers=headers).json()["data"]["items"]
    legacy_used_item = legacy_items[0]
    assert legacy_used_item["status"] == "USED"
    assert legacy_used_item["used_by_name"] is None


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


def test_list_company_invites_returns_404_for_missing_company(api_client) -> None:
    """P3-9：不存在的公司请求邀请记录必须 404，不得用空列表冒充。"""

    client, _ = api_client
    headers = _admin_headers(client)
    response = client.get("/api/v1/auth/companies/nonexistent-company/invites", headers=headers)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "COMPANY_NOT_AVAILABLE"


def test_list_company_invites_rejects_authenticated_non_admin(api_client) -> None:
    """P3-9：已认证但无 * 权限的内部账号同样被拒；401 之外补齐 403 分支。"""

    client, factory = api_client
    with factory() as db:
        create_internal_user(
            db, username="list-tel", password="Telesales9!", display_name="电销", role_code="TELESALES"
        )
        db.commit()
    login = client.post("/api/v1/auth/login", json={"username": "list-tel", "password": "Telesales9!"})
    assert login.status_code == 200, login.text
    token = login.cookies.get("access_token")
    assert token
    response = client.get(
        "/api/v1/auth/companies/any-company/invites",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"


def test_list_company_invites_returns_desc_order_and_caps_at_50(api_client) -> None:
    """P3-9：列表按创建时间降序且上限 50 条；更早的历史行会滑出窗口。"""

    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        company = create_company(db, _company_body("SH-LIST-CAP"))
        db.flush()
        # 直插 52 条已使用历史行，序号写入快照列，断言窗口裁掉的是最旧两条。
        for index in range(52):
            db.add(
                InviteToken(
                    token_hash=hash_token(f"list-cap-{index:02d}"),
                    company_id=company.id,
                    expires_at=utcnow() - timedelta(hours=1),
                    used_at=utcnow() - timedelta(hours=2),
                    invitee_name_snapshot=f"负责人{index:02d}",
                    created_at=utcnow() - timedelta(minutes=52 - index),
                )
            )
        db.commit()
        company_id = company.id

    items = client.get(f"/api/v1/auth/companies/{company_id}/invites", headers=headers).json()["data"]["items"]
    assert len(items) == 50
    assert [item["invitee_name"] for item in items[:3]] == ["负责人51", "负责人50", "负责人49"]
    assert items[-1]["invitee_name"] == "负责人02"
    names = {item["invitee_name"] for item in items}
    assert "负责人00" not in names
    assert "负责人01" not in names


def test_list_company_invites_expired_boundary_matches_validation(api_client) -> None:
    """P3-9：expires_at 已到点的行列表判 EXPIRED，验证通道同步拒绝，两侧口径一致。"""

    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        company = create_company(db, _company_body("SH-LIST-BOUND"))
        db.flush()
        # 写入时刻即过期：列表判定为 as_utc(expires_at) <= now，与 validate 同一口径。
        db.add(
            InviteToken(
                token_hash=hash_token("list-boundary-expired"),
                company_id=company.id,
                expires_at=utcnow(),
            )
        )
        db.commit()
        company_id = company.id

    items = client.get(f"/api/v1/auth/companies/{company_id}/invites", headers=headers).json()["data"]["items"]
    assert [item["status"] for item in items] == ["EXPIRED"]

    with factory() as db:
        _expect_invite_invalid(lambda: validate_invite(db, raw_token="list-boundary-expired"))


def test_list_company_invites_attributes_primary_only_to_latest_used(api_client) -> None:
    """N9：归因来自消费时刻的 used_by_user_id，不随主账号换绑漂移——
    历史邀请不得因数据修复/人工换绑被重新归因到新账号。"""

    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        company = create_company(db, _company_body("SH-P36-USED"))
        _, raw, _ = create_company_invite(db, company.id, None, 24)
        bind_wechat_by_invite(db, raw, "openid-p3-06", "李老板")
        db.commit()
        # 换绑前的历史行：used_at 有值但无法核实使用者（N9 前的存量数据）
        db.add(
            InviteToken(
                token_hash=hash_token("p3-06-legacy-used-token-0001"),
                company_id=company.id,
                expires_at=utcnow() + timedelta(hours=1),
                used_at=utcnow() - timedelta(days=3),
            )
        )
        # 模拟人工换绑：主账号被指到新用户（数据修复场景）
        replacement = User(display_name="新主账号", company_id=company.id, status="ACTIVE")
        db.add(replacement)
        db.flush()
        company.primary_user_id = replacement.id
        db.commit()
        company_id = company.id

    items = client.get(f"/api/v1/auth/companies/{company_id}/invites", headers=headers).json()["data"]["items"]
    used_rows = [item for item in items if item["status"] == "USED"]
    named = [item for item in used_rows if item["used_by_name"]]
    assert len(used_rows) == 2
    # 只有绑定流真实消费的邀请有归因，且是当时的真实使用者，不是新主账号
    assert len(named) == 1
    assert named[0]["used_by_name"] == "李老板"


def test_validate_invite_rejects_mismatched_token_and_id(db) -> None:
    """I13：双参同给且指向不同邀请时，validate 与 consume 同口径拒绝，不再 raw 静默优先。"""

    company = create_company(db, _company_body("SH-I13-VALID"))
    first = _legacy_invite(db, company.id, "i13-first-raw-token-0001")
    second = _legacy_invite(db, company.id, "i13-second-raw-token-0002")

    # 单参与双参一致：都解析到同一条邀请
    assert validate_invite(db, raw_token="i13-first-raw-token-0001").id == first.id
    assert validate_invite(db, invite_id=first.id).id == first.id
    assert validate_invite(db, raw_token="i13-first-raw-token-0001", invite_id=first.id).id == first.id
    # 双参指向不同邀请：与 _consume_invite 的 AND 语义对齐，显式 AUTH_INVITE_INVALID
    _expect_invite_invalid(lambda: validate_invite(db, raw_token="i13-first-raw-token-0001", invite_id=second.id))
    _expect_invite_invalid(lambda: validate_invite(db, raw_token="not-a-real-token", invite_id=first.id))


def test_confirm_start_rate_limits_repeated_anonymous_requests(api_client) -> None:
    """I15：匿名 confirm-start 按 invite+IP 限流，持有效邀请也不能循环刷审计写入。"""

    client, factory = api_client
    with factory() as db:
        company = create_company(db, _company_body("SH-I15-RATE"))
        _, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite = raw

    responses = [
        client.post(
            "/api/v1/auth/invites/confirm-start",
            json={"invite": invite, "return_url": "/h5/#/home"},
            headers={"x-real-ip": "203.0.113.15"},
        )
        for _ in range(11)
    ]
    # 前 10 次正常处理（本用例的邀请有效，应全部 OK），第 11 次触发限流；
    # N11：限流必须是真 429，业务码不得挤进 200 信封。
    assert [r.json()["code"] for r in responses[:10]] == ["OK"] * 10
    assert responses[10].status_code == 429
    assert responses[10].json()["code"] == "AUTH_RATE_LIMITED"


def test_confirm_start_rate_limit_survives_x_real_ip_spoofing(api_client) -> None:
    """N1：默认不信任代理头——轮换 x-real-ip 不能重置限流桶（真实直连场景）。"""

    client, factory = api_client
    with factory() as db:
        company = create_company(db, _company_body("SH-N1-SPOOF"))
        _, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite = raw

    for i in range(11):
        resp = client.post(
            "/api/v1/auth/invites/confirm-start",
            json={"invite": invite, "return_url": "/h5/#/home"},
            headers={"x-real-ip": f"198.51.100.{i}"},  # 每次伪造不同源 IP
        )
        if i < 10:
            assert resp.json()["code"] == "OK"
        else:
            assert resp.status_code == 429, resp.text
            assert resp.json()["code"] == "AUTH_RATE_LIMITED"


def test_confirm_start_rate_limit_honors_proxy_ip_when_trusted(api_client, monkeypatch) -> None:
    """N1：显式信任反代时，x-real-ip 才参与限流键（换头 = 换真实来源）。"""

    import apps.api.src.routers.auth as auth_router

    monkeypatch.setattr(auth_router.settings, "trust_proxy_headers", True)
    client, factory = api_client
    with factory() as db:
        company = create_company(db, _company_body("SH-N1-TRUST"))
        _, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite = raw

    def post(ip: str):
        return client.post(
            "/api/v1/auth/invites/confirm-start",
            json={"invite": invite, "return_url": "/h5/#/home"},
            headers={"x-real-ip": ip},
        )

    for _ in range(10):
        assert post("203.0.113.15").json()["code"] == "OK"
    assert post("203.0.113.15").status_code == 429
    # 信任代理头时，反代注入的新 x-real-ip 是新桶，不受前一个 IP 拖累
    assert post("203.0.113.99").json()["code"] == "OK"


def test_confirm_start_rate_limit_recovers_after_window(api_client, monkeypatch) -> None:
    """I15：滑窗过期后桶释放，正常请求恢复放行（限流不是永久封禁）。"""

    import time as time_module

    import apps.api.src.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "_CONFIRM_START_WINDOW_SECONDS", 3.0)
    client, factory = api_client
    with factory() as db:
        company = create_company(db, _company_body("SH-I15-WIN"))
        _, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite = raw

    def post():
        return client.post(
            "/api/v1/auth/invites/confirm-start",
            json={"invite": invite, "return_url": "/h5/#/home"},
        )

    for _ in range(10):
        assert post().json()["code"] == "OK"
    assert post().status_code == 429
    time_module.sleep(3.1)  # 越过被压缩的滑窗
    assert post().json()["code"] == "OK"


def test_confirm_start_buckets_are_bounded_and_fail_closed() -> None:
    """N8：桶容量有硬上限，超限时 fail-closed 拒绝新键而不是无界扩张。"""

    import time as time_module

    import apps.api.src.routers.auth as auth_router

    buckets = auth_router._CONFIRM_START_BUCKETS
    buckets.clear()
    try:
        for i in range(auth_router._CONFIRM_START_MAX_BUCKETS):
            buckets[f"filler:{i}"] = [time_module.monotonic()]
        assert auth_router._confirm_start_rate_limited("fresh-invite-token-001", "203.0.113.7") is True
        assert len(buckets) <= auth_router._CONFIRM_START_MAX_BUCKETS
        # 桶内时间戳全部越过窗口后，清扫释放容量，新键恢复放行
        stale = time_module.monotonic() - auth_router._CONFIRM_START_WINDOW_SECONDS - 1
        for key in buckets:
            buckets[key] = [stale]
        assert auth_router._confirm_start_rate_limited("fresh-invite-token-001", "203.0.113.7") is False
    finally:
        buckets.clear()


def test_confirm_start_ip_dimension_caps_bucket_creation() -> None:
    """M-A：单 IP 用随机 invite 也撞不满桶表——IP 维度硬性封顶后仅拒绝该 IP
    自己的后续请求，其他 IP 的真实用户不受任何拖累。"""

    import apps.api.src.routers.auth as auth_router

    buckets = auth_router._CONFIRM_START_BUCKETS
    ip_buckets = auth_router._CONFIRM_START_IP_BUCKETS
    buckets.clear()
    ip_buckets.clear()
    try:
        for i in range(auth_router._CONFIRM_START_MAX_PER_IP_PER_WINDOW):
            assert (
                auth_router._confirm_start_rate_limited(f"ip-cap-invite-{i:04d}", "198.51.100.9")
                is False
            )
        # 同一 IP 超过窗口内请求上限：拒绝，且无法再新建 invite 桶
        assert auth_router._confirm_start_rate_limited("ip-cap-invite-overflow", "198.51.100.9") is True
        # 其他 IP 不受拖累，真实用户仍可正常确认
        assert auth_router._confirm_start_rate_limited("ip-cap-invite-other", "198.51.100.10") is False
    finally:
        buckets.clear()
        ip_buckets.clear()


def test_confirm_start_rate_limit_is_thread_safe() -> None:
    """M-A：并发 burst 下同键窗口内放行数恰好等于上限——读改写整体持锁，
    多线程不再同时通过计数检查让限流被绕过。"""

    from concurrent.futures import ThreadPoolExecutor

    import apps.api.src.routers.auth as auth_router

    buckets = auth_router._CONFIRM_START_BUCKETS
    ip_buckets = auth_router._CONFIRM_START_IP_BUCKETS
    buckets.clear()
    ip_buckets.clear()
    try:
        def attempt(_: int) -> bool:
            return auth_router._confirm_start_rate_limited("thread-safe-invite-0001", "203.0.113.77")

        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(attempt, range(60)))
        allowed = sum(1 for limited in results if limited is False)
        assert allowed == auth_router._CONFIRM_START_MAX_PER_WINDOW
    finally:
        buckets.clear()
        ip_buckets.clear()

def test_identity_hit_relogin_consumes_invite_with_real_user(db) -> None:
    """N9：已绑定身份带新邀请重登（防御路径）——消费同样写回真实使用者。"""

    company = create_company(db, _company_body("SH-N9-RELOGIN"))
    _, raw, _ = create_company_invite(db, company.id, None, 24)
    user, _ = bind_wechat_by_invite(db, raw, "openid-n9-relogin", "王老板")
    db.commit()
    # 已绑定公司不能再发新邀请，直接造行模拟并发/修复窗口的存量邀请
    fresh = InviteToken(
        token_hash=hash_token("n9-relogin-fresh-token-0001"),
        company_id=company.id,
        expires_at=utcnow() + timedelta(hours=1),
    )
    db.add(fresh)
    db.commit()

    login_or_bind_wechat(db, openid="openid-n9-relogin", nickname="王老板", invite_token="n9-relogin-fresh-token-0001")
    db.commit()
    assert fresh.used_at is not None
    assert fresh.used_by_user_id == user.id
