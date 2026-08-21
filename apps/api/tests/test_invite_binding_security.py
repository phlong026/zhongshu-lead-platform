from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from apps.api.src.core.errors import AppError
from apps.api.src.core.invite_models import InviteBindingProfile, InviteConfirmationIntent
from apps.api.src.core.models import Company, InviteToken, Role, User, WechatIdentity
from apps.api.src.core.security import create_signed_state
from apps.api.src.core.time import utcnow
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.invite_binding_service import (
    bind_wechat_with_confirmation,
    create_company_invite,
    create_confirmation_intent,
    list_invites,
    match_company_by_phone,
    manual_match_companies,
    preview_company_invite,
    revoke_invite,
)
from apps.api.src.services.invite_delivery import prepare_invite_delivery


def _company(db, code: str, name: str, owner_name: str | None = "张老板", phone: str | None = None):
    company = create_company(
        db,
        CompanyCreateBody(
            code=code,
            name=name,
            owner_name=owner_name,
            contact_phone=phone,
            region_codes=["310000"],
            capabilities=[{"category_code": "OLD_RENOVATION", "brand_code": "ZHONGSHU"}],
        ),
    )
    db.flush()
    return company


def _confirmation(db, company: Company):
    created = create_company_invite(db, company.id, None, 24)
    started = create_confirmation_intent(db, created.raw_token, "/h5/#/home")
    db.flush()
    return created, started


def test_invite_creation_returns_snapshots_copy_text_and_owner_fallback(db) -> None:
    company = _company(db, "INV001", "上海一号加盟商", owner_name=None)

    created = create_company_invite(db, company.id, None, 24)
    db.commit()

    assert created.owner_name == "该公司负责人"
    assert created.company_name == "上海一号加盟商"
    assert created.invite_url.startswith("http")
    assert created.raw_token not in created.copy_text.replace(created.invite_url, "")
    assert "该公司负责人" in created.copy_text
    assert "上海一号加盟商" in created.copy_text
    assert created.invite_url in created.copy_text
    assert created.status == "ACTIVE"
    profile = db.get(InviteBindingProfile, created.invite.id)
    assert profile is not None
    assert profile.company_name_snapshot == "上海一号加盟商"
    assert profile.owner_name_snapshot is None


def test_new_invite_revokes_previous_active_invite_and_preserves_snapshot(db) -> None:
    company = _company(db, "INV002", "原公司名称")
    first = create_company_invite(db, company.id, None, 24)
    company.name = "修改后的公司名称"
    second = create_company_invite(db, company.id, None, 24)
    db.commit()

    db.refresh(first.invite)
    assert first.invite.revoked_at is not None
    assert preview_company_invite(db, second.raw_token)["company_name"] == "修改后的公司名称"
    first_profile = db.get(InviteBindingProfile, first.invite.id)
    assert first_profile.company_name_snapshot == "原公司名称"


def test_company_status_is_consistent_for_create_preview_and_binding(db) -> None:
    company = _company(db, "INV003", "停用公司")
    created, started = _confirmation(db, company)
    company.status = "DISABLED"
    db.commit()

    with pytest.raises(AppError) as create_error:
        create_company_invite(db, company.id, None, 24)
    assert create_error.value.code == "AUTH_COMPANY_UNAVAILABLE"

    with pytest.raises(AppError) as preview_error:
        preview_company_invite(db, created.raw_token)
    assert preview_error.value.code == "AUTH_COMPANY_UNAVAILABLE"

    with pytest.raises(AppError) as bind_error:
        bind_wechat_with_confirmation(db, started.confirmation_intent, openid="wx-disabled")
    assert bind_error.value.code == "AUTH_COMPANY_UNAVAILABLE"


def test_revoked_expired_and_used_invites_are_rejected(db) -> None:
    company = _company(db, "INV004", "邀请状态公司")

    revoked = create_company_invite(db, company.id, None, 24)
    revoke_invite(db, revoked.invite.id)
    with pytest.raises(AppError) as revoked_error:
        preview_company_invite(db, revoked.raw_token)
    assert revoked_error.value.code == "AUTH_INVITE_REVOKED"

    expired = create_company_invite(db, company.id, None, 24)
    expired.invite.expires_at = utcnow() - timedelta(seconds=1)
    db.flush()
    with pytest.raises(AppError) as expired_error:
        preview_company_invite(db, expired.raw_token)
    assert expired_error.value.code == "AUTH_INVITE_EXPIRED"

    used = create_company_invite(db, company.id, None, 24)
    used.invite.used_at = utcnow()
    db.flush()
    with pytest.raises(AppError) as used_error:
        preview_company_invite(db, used.raw_token)
    assert used_error.value.code == "AUTH_INVITE_USED"


def test_confirmation_intent_has_independent_purpose_expiry_and_replay_protection(db) -> None:
    company = _company(db, "INV005", "Intent 公司")
    _, started = _confirmation(db, company)

    ordinary_state = create_signed_state(
        {"return_url": "/h5/#/home"},
        purpose="wechat-oauth",
    )
    with pytest.raises(AppError) as purpose_error:
        bind_wechat_with_confirmation(db, ordinary_state, openid="wx-purpose")
    assert purpose_error.value.code == "AUTH_CONFIRMATION_INTENT_INVALID"

    intent_row = db.get(InviteConfirmationIntent, started.intent_id)
    intent_row.expires_at = utcnow() - timedelta(seconds=1)
    db.flush()
    with pytest.raises(AppError) as expiry_error:
        bind_wechat_with_confirmation(db, started.confirmation_intent, openid="wx-expired")
    assert expiry_error.value.code == "AUTH_CONFIRMATION_INTENT_EXPIRED"

    intent_row.expires_at = utcnow() + timedelta(minutes=5)
    db.flush()
    user, _, _ = bind_wechat_with_confirmation(
        db,
        started.confirmation_intent,
        openid="wx-replay",
        nickname="张老板",
    )
    db.commit()
    assert user.company_id == company.id

    with pytest.raises(AppError) as replay_error:
        bind_wechat_with_confirmation(db, started.confirmation_intent, openid="wx-replay")
    assert replay_error.value.code == "AUTH_CONFIRMATION_INTENT_USED"


def test_tampered_company_id_in_confirmation_intent_is_rejected(db) -> None:
    company = _company(db, "INV006", "目标公司")
    other = _company(db, "INV007", "篡改公司")
    _, started = _confirmation(db, company)
    row = db.get(InviteConfirmationIntent, started.intent_id)
    forged = create_signed_state(
        {
            "intent_id": row.id,
            "nonce": started.nonce_for_test,
            "invite_id": row.invite_id,
            "company_id": other.id,
            "binding_confirmed": True,
            "return_url": "/h5/#/home",
        },
        purpose="wechat-oauth-bind",
    )

    with pytest.raises(AppError) as exc:
        bind_wechat_with_confirmation(db, forged, openid="wx-tampered")
    assert exc.value.code == "AUTH_CONFIRMATION_INTENT_INVALID"


def test_existing_primary_user_cannot_be_overwritten_and_invite_remains_unused(db) -> None:
    company = _company(db, "INV008", "主账号保护公司")
    created, started = _confirmation(db, company)
    role = db.scalar(select(Role).where(Role.code == "FRANCHISE_OWNER"))
    existing = User(display_name="原主账号", company_id=company.id, roles=[role])
    db.add(existing)
    db.flush()
    company.primary_user_id = existing.id
    db.commit()

    with pytest.raises(AppError) as exc:
        bind_wechat_with_confirmation(db, started.confirmation_intent, openid="wx-new-owner")
    db.rollback()
    assert exc.value.code == "AUTH_COMPANY_ALREADY_BOUND"
    assert db.get(Company, company.id).primary_user_id == existing.id
    assert db.get(InviteToken, created.invite.id).used_at is None
    assert db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "wx-new-owner")) is None


def test_wechat_bound_to_other_company_is_rejected_without_side_effects(db) -> None:
    target = _company(db, "INV009", "目标公司")
    other = _company(db, "INV010", "既有公司")
    created, started = _confirmation(db, target)
    role = db.scalar(select(Role).where(Role.code == "FRANCHISE_OWNER"))
    existing = User(display_name="其他公司用户", company_id=other.id, roles=[role])
    db.add(existing)
    db.flush()
    db.add(WechatIdentity(openid="wx-other-company", user_id=existing.id))
    db.commit()

    with pytest.raises(AppError) as exc:
        bind_wechat_with_confirmation(db, started.confirmation_intent, openid="wx-other-company")
    db.rollback()
    assert exc.value.code == "AUTH_WECHAT_BOUND_OTHER_COMPANY"
    assert db.get(InviteToken, created.invite.id).used_at is None
    assert db.get(Company, target.id).primary_user_id is None


def test_failed_binding_transaction_rolls_back_all_rows(db, monkeypatch) -> None:
    import apps.api.src.services.invite_binding_service as service

    company = _company(db, "INV011", "回滚公司")
    created, started = _confirmation(db, company)
    db.commit()

    def fail_identity(*args, **kwargs):
        raise RuntimeError("synthetic identity insert failure")

    monkeypatch.setattr(service, "_add_wechat_identity", fail_identity)
    with pytest.raises(RuntimeError):
        bind_wechat_with_confirmation(db, started.confirmation_intent, openid="wx-rollback")
    db.rollback()

    assert db.get(Company, company.id).primary_user_id is None
    assert db.get(InviteToken, created.invite.id).used_at is None
    assert db.get(InviteConfirmationIntent, started.intent_id).used_at is None
    assert db.scalar(select(User).where(User.display_name == "微信加盟商")) is None
    assert db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "wx-rollback")) is None


def test_invite_list_is_paginated_filterable_and_revoke_missing_is_404(db) -> None:
    company = _company(db, "INV012", "列表公司")
    first = create_company_invite(db, company.id, None, 24)
    second = create_company_invite(db, company.id, None, 24)
    db.commit()

    items, total = list_invites(db, company_id=company.id, status="ACTIVE", page_no=1, page_size=1)
    assert total == 1
    assert len(items) == 1
    assert items[0]["invite_id"] == second.invite.id
    assert items[0]["company_name"] == "列表公司"
    assert items[0]["status"] == "ACTIVE"
    assert db.get(InviteToken, first.invite.id).revoked_at is not None

    with pytest.raises(AppError) as exc:
        revoke_invite(db, "missing-invite")
    assert exc.value.code == "AUTH_INVITE_NOT_FOUND"
    assert exc.value.status_code == 404


def test_phone_and_manual_matching_do_not_expose_plain_phone(db) -> None:
    company = _company(db, "INV013", "手机号匹配公司", phone="13800138013")
    db.commit()

    matched = match_company_by_phone(db, "138 0013 8013")
    assert matched["outcome"] == "UNIQUE"
    assert matched["company"]["id"] == company.id
    assert "phone" not in str(matched).lower()
    assert "13800138013" not in str(matched)

    items, total = manual_match_companies(
        db,
        query="手机号匹配",
        region_code="310000",
        page_no=1,
        page_size=20,
    )
    assert total == 1
    assert items[0]["id"] == company.id


def test_delivery_defaults_are_prepared_or_explicitly_disabled(db) -> None:
    company = _company(db, "INV014", "发送适配公司")
    created = create_company_invite(db, company.id, None, 24)
    db.commit()

    copied = prepare_invite_delivery(db, created.invite.id, "COPY", requested_by=None)
    assert copied.status == "PREPARED"
    assert copied.delivered is False
    assert copied.payload["copy_text"] == created.copy_text

    qr = prepare_invite_delivery(db, created.invite.id, "QRCODE", requested_by=None)
    assert qr.status == "PREPARED"
    assert qr.delivered is False
    assert qr.payload["invite_url"] == created.invite_url

    with pytest.raises(AppError) as exc:
        prepare_invite_delivery(db, created.invite.id, "SMS", requested_by=None)
    assert exc.value.code == "INVITE_DELIVERY_CHANNEL_DISABLED"
