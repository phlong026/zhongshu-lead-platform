import json

from sqlalchemy import select

import apps.api.src.integrations.wechat as wechat_module
from apps.api.src.core.models import NotificationOutbox, SystemConfig
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.notification_service import enqueue_outbox
from apps.api.src.services.outbox_worker import process_outbox


def test_outbox_without_recipient_is_retried(db) -> None:
    item=enqueue_outbox(db,event_key="test:event",event_type="ASSIGNMENT_DISPATCHED",aggregate_type="assignment",aggregate_id="a1",payload={})
    db.commit()
    result=process_outbox(db)
    db.commit()
    assert result["failed"]==1
    assert item.status=="FAILED"
    assert item.attempts==1


def test_outbox_event_key_is_idempotent(db) -> None:
    one=enqueue_outbox(db,event_key="same:event",event_type="X",aggregate_type="x",aggregate_id="1",payload={})
    two=enqueue_outbox(db,event_key="same:event",event_type="X",aggregate_type="x",aggregate_id="1",payload={})
    assert one.id==two.id


def _invite_outbox_setup(api_client, monkeypatch=None):
    """Create one company + invite over HTTP; return (client, factory, invite_id, raw_token)."""

    client, factory = api_client
    if monkeypatch is not None:
        monkeypatch.setattr(wechat_module.settings, "wechat_dev_mock", False)
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin123!"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.cookies.get('access_token')}"}
    with factory() as db:
        company = create_company(
            db,
            CompanyCreateBody(
                code="SH-OUTBOX",
                name="通知测试公司",
                owner_name="李负责人",
                region_codes=["310100"],
                capabilities=[{"category_code": "OLD_RENOVATION", "brand_code": None}],
            ),
        )
        db.commit()
        company_id = company.id
    data = client.post(
        f"/api/v1/auth/companies/{company_id}/invites", headers=headers, json={"expires_hours": 24}
    ).json()["data"]
    return client, factory, data["invite_id"], data["token"]


def test_create_invite_enqueues_outbox_event_without_raw_token(api_client) -> None:
    """P2-03：创建邀请事务内入队 INVITE_CREATED；事件绝不携带 raw token。"""

    client, factory, invite_id, raw_token = _invite_outbox_setup(api_client)
    with factory() as db:
        item = db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_type == "INVITE_CREATED"))
        assert item is not None
        assert item.event_key == f"invite:{invite_id}:created"
        assert item.status == "PENDING"
        assert item.payload["company_name"] == "通知测试公司"
        assert item.payload["invitee_name"] == "李负责人"
        assert item.payload["deep_link"] == "/h5/#/login"
        # 安全红线：raw token 不落 Outbox（失败队列/DB 都不暴露邀请原文）。
        assert raw_token not in json.dumps(item.payload, ensure_ascii=False)


def test_invite_outbox_delivers_through_dev_mock(api_client) -> None:
    """P2-03：dev mock 通道把邀请事件渲染成模板消息并标记 SENT。"""

    client, factory, invite_id, _ = _invite_outbox_setup(api_client)
    with factory() as db:
        result = process_outbox(db)
        db.commit()
        # seed_demo 预置演示事件也会被投递，只断言 INVITE_CREATED 这一条。
        assert result["sent"] >= 1, result
        item = db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_type == "INVITE_CREATED"))
        assert item is not None and item.status == "SENT"
        assert item.last_error is None


def test_invite_outbox_real_mode_without_template_fails_clearly(api_client, monkeypatch) -> None:
    """P2-03：真实通道未发布模板时明确失败，成为「渠道未接入」的可见信号。"""

    client, factory, invite_id, _ = _invite_outbox_setup(api_client, monkeypatch)
    with factory() as db:
        result = process_outbox(db)
        db.commit()
        assert result["failed"] >= 1, result
        item = db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_type == "INVITE_CREATED"))
        assert item is not None and item.status == "FAILED"
        assert "TEMPLATE_NOT_CONFIGURED" in (item.last_error or "")


def test_invite_outbox_real_mode_with_template_reports_no_recipient(api_client, monkeypatch) -> None:
    """S1：真实通道 + 已发布模板时，占位收件人快速失败为 NO_RECIPIENT。"""

    client, factory, invite_id, _ = _invite_outbox_setup(api_client, monkeypatch)
    with factory() as db:
        db.add(
            SystemConfig(
                domain="wechat_template",
                key="INVITE_CREATED",
                status="PUBLISHED",
                value_json={"template_id": "TMPL-INVITE-TEST"},
            )
        )
        db.commit()
        result = process_outbox(db)
        db.commit()
        assert result["failed"] >= 1, result
        item = db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_type == "INVITE_CREATED"))
        assert item is not None and item.status == "FAILED"
        assert "NO_RECIPIENT" in (item.last_error or "")


def test_outbox_failure_text_never_persists_credentials(db, monkeypatch) -> None:
    """N3：外发异常原文携带微信凭据 URL 时，last_error 落库前必须脱敏。"""

    from apps.api.src.core.models import User, WechatIdentity
    from apps.api.src.integrations.wechat import WechatOfficialAccountClient

    user = User(display_name="通知负责人", status="ACTIVE")
    db.add(user)
    db.flush()
    db.add(WechatIdentity(openid="o-outbox-leak", user_id=user.id))
    item = enqueue_outbox(
        db,
        event_key="test:leak",
        event_type="ASSIGNMENT_DISPATCHED",
        aggregate_type="assignment",
        aggregate_id="a-leak",
        payload={"user_id": user.id},
    )
    db.commit()

    def raise_with_credential_url(self, **kwargs):
        raise RuntimeError(
            "Client error '400 Bad Request' for url "
            "'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token=71_AbCdSECRET_TOKEN&x=1'"
        )

    monkeypatch.setattr(WechatOfficialAccountClient, "send_scene_message", raise_with_credential_url)
    process_outbox(db)
    db.commit()
    assert item.status == "FAILED", ("status", item.status, "last_error", item.last_error, "attempts", item.attempts)
    assert "71_AbCdSECRET_TOKEN" not in (item.last_error or ""), item.last_error
    assert "access_token=***" in item.last_error, item.last_error  # 键名保留、值打码
    assert "RuntimeError" in item.last_error, "异常类名保留供排障"


def test_failed_outbox_response_scrubs_legacy_poisoned_last_error(api_client) -> None:
    """N3：存量脏 last_error 经 failed-outbox 出参时同样脱敏。"""

    client, factory = api_client
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin123!"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.cookies.get('access_token')}"}
    with factory() as db:
        item = enqueue_outbox(
            db,
            event_key="test:legacy-poison",
            event_type="ASSIGNMENT_DISPATCHED",
            aggregate_type="assignment",
            aggregate_id="1",
            payload={},
        )
        item.status = "FAILED"
        item.last_error = (
            "Client error '401' for url 'https://api.weixin.qq.com/cgi-bin/token?appid=wx123&secret=RAW_SECRET_9f'"
        )
        db.commit()
    resp = client.get("/api/v1/notifications/outbox/failed", headers=headers)
    assert resp.status_code == 200, resp.text
    assert "RAW_SECRET_9f" not in resp.text
    assert "access_token" not in resp.text or "***" in resp.text
