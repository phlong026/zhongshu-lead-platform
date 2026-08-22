from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import Company, WechatIdentity
from apps.api.src.services.auth_service import bind_wechat_by_invite, create_company_invite
from apps.api.src.services.binding_integrity import audit_primary_binding_integrity
from apps.api.src.services.company_service import create_company
# I19/N13：建司样板与 test_auth_company 单一来源，不再整段复制。
from test_auth_company import _company_body


def _bind_owner(db, code: str, openid: str):
    company = create_company(db, _company_body(code))
    _, raw, _ = create_company_invite(db, company.id, None, 24)
    user, _ = bind_wechat_by_invite(db, raw, openid, "张老板")
    db.commit()
    return company, user


def _codes(report) -> set[str]:
    return {issue["code"] for issue in report.issues}


def test_clean_binding_passes_integrity_audit(db) -> None:
    """I16 正向不变量：正常绑定流落库后，主账号指向在册用户且证据齐全。"""
    company, user = _bind_owner(db, "I16-CLEAN", "openid-i16-clean")

    report = audit_primary_binding_integrity(db)

    assert report.checked_companies >= 1
    assert report.issues == []
    assert report.valid
    stored = db.get(Company, company.id)
    assert stored.primary_user_id == user.id


def test_dangling_primary_is_reported_as_error(db) -> None:
    """I16 场景一：primary 指向不存在用户 → 公司被悬空指针锁死，核查必须报 error。"""
    company, _user = _bind_owner(db, "I16-DANGLING", "openid-i16-dangling")
    company.primary_user_id = "ghost-user-id-not-exists"
    db.commit()

    report = audit_primary_binding_integrity(db)

    assert "DANGLING_PRIMARY" in _codes(report)
    assert not report.valid


def test_cleared_primary_with_identity_is_reported(db) -> None:
    """I16 场景二：primary 被误清空而旧微信身份仍在 → 可绑第二个负责人，核查必须报 error。"""
    company, _user = _bind_owner(db, "I16-CLEARED", "openid-i16-cleared")
    company.primary_user_id = None
    db.commit()
    # 误清空不清理身份：旧微信身份仍挂在该公司成员上
    assert db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "openid-i16-cleared"))

    report = audit_primary_binding_integrity(db)

    assert "ORPHAN_OWNER_IDENTITY" in _codes(report)
    assert not report.valid


def test_shared_primary_across_companies_is_reported(db) -> None:
    """I16：同一用户被两家公司登记为主账号（含身份串号），核查必须同时报两处 error。"""
    first, user = _bind_owner(db, "I16-SHARE-A", "openid-i16-share")
    second = create_company(db, _company_body("I16-SHARE-B"))
    second.primary_user_id = user.id
    db.commit()

    report = audit_primary_binding_integrity(db)

    codes = _codes(report)
    assert "SHARED_PRIMARY" in codes
    assert "PRIMARY_USER_COMPANY_MISMATCH" in codes
    assert not report.valid
    # group by 无 order by，company_ids 顺序不保证：按集合存在性断言，
    # 不依赖返回顺序（合跑时 SQLite 查询计划与单跑不同）。
    shared = [
        issue
        for issue in report.issues
        if issue["code"] == "SHARED_PRIMARY"
        and set(issue["details"]["company_ids"]) == {first.id, second.id}
    ]
    assert shared, "本测试造的跨公司共享主账号未被报告"


def test_primary_without_identity_is_error(db) -> None:
    """N2：主账号缺微信身份 = 公司「已绑定」却无法微信登录、无法重新邀请、
    通知必败——不再是 warning，必须 error 并阻断 valid（发布门禁）。"""
    company, _user = _bind_owner(db, "I16-NOIDENT", "openid-i16-noident")
    identity = db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "openid-i16-noident"))
    db.delete(identity)
    db.commit()

    report = audit_primary_binding_integrity(db)

    assert _codes(report) == {"PRIMARY_WITHOUT_IDENTITY"}
    assert not report.valid
