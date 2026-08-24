import json

from sqlalchemy import select

import apps.api.src.integrations.wechat as wechat_module
from apps.api.src.core.models import NotificationOutbox, SystemConfig
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.notification_service import enqueue_outbox
from apps.api.src.services.outbox_worker import process_outbox
# I19/N13：admin 登录头与 test_auth_company 单一来源，不再手写样板。
from test_auth_company import _admin_headers


def test_outbox_without_recipient_is_retried(db) -> None:
    """N7：无收件人是确定性失败——重试不可能让用户凭空绑定微信，
    直接终态化 MANUAL_ACTION_REQUIRED；运营核实后经重试按钮手动重置。"""
    item=enqueue_outbox(db,event_key="test:event",event_type="ASSIGNMENT_DISPATCHED",aggregate_type="assignment",aggregate_id="a1",payload={})
    db.commit()
    result=process_outbox(db)
    db.commit()
    assert result["manual"]==1
    assert item.status=="MANUAL_ACTION_REQUIRED"
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
    headers = _admin_headers(client)
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


def test_invite_outbox_delivers_through_dev_mock(api_client, monkeypatch) -> None:
    """P2-03：dev mock 通道把邀请事件渲染成模板消息并标记 SENT。"""

    monkeypatch.setattr(wechat_module.settings, "wechat_dev_mock", True)
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
    """P2-03/N7：真实通道未发布模板是确定性配置错误——直接终态化
    MANUAL_ACTION_REQUIRED 交运营兜底，不再空转 5 次退避重试。"""

    client, factory, invite_id, _ = _invite_outbox_setup(api_client, monkeypatch)
    with factory() as db:
        result = process_outbox(db)
        db.commit()
        assert result["manual"] >= 1, result
        item = db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_type == "INVITE_CREATED"))
        assert item is not None and item.status == "MANUAL_ACTION_REQUIRED"
        assert "TEMPLATE_NOT_CONFIGURED" in (item.last_error or "")
        # 终态不再被下一轮处理扫描，attempts 不涨
        process_outbox(db)
        db.commit()
        assert item.attempts == 1


def test_invite_outbox_real_mode_with_template_reports_no_recipient(api_client, monkeypatch) -> None:
    """S1/N7：真实通道 + 已发布模板时占位收件人必败——NO_RECIPIENT 同样
    终态化为 MANUAL_ACTION_REQUIRED，由运营经创建弹窗人工发送兜底。"""

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
        assert result["manual"] >= 1, result
        item = db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_type == "INVITE_CREATED"))
        assert item is not None and item.status == "MANUAL_ACTION_REQUIRED"
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
    headers = _admin_headers(client)
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


def test_failed_outbox_panel_defaults_include_terminal_states(api_client) -> None:
    """N7：失败面板默认必须涵盖 FAILED/DEAD/MANUAL_ACTION_REQUIRED——
    DEAD 与人工终态从面板消失等于静默丢失运维信号。"""

    client, factory = api_client
    headers = _admin_headers(client)
    with factory() as db:
        for key, status in (
            ("test:panel-failed", "FAILED"),
            ("test:panel-dead", "DEAD"),
            ("test:panel-manual", "MANUAL_ACTION_REQUIRED"),
        ):
            item = enqueue_outbox(
                db, event_key=key, event_type="ASSIGNMENT_DISPATCHED", aggregate_type="a", aggregate_id="1", payload={}
            )
            item.status = status
        db.commit()

    resp = client.get("/api/v1/notifications/outbox/failed", headers=headers)
    assert resp.status_code == 200, resp.text
    statuses = {row["status"] for row in resp.json()["data"]}
    assert statuses == {"FAILED", "DEAD", "MANUAL_ACTION_REQUIRED"}

    # 显式过滤保留精确语义
    resp = client.get("/api/v1/notifications/outbox/failed?status=FAILED", headers=headers)
    assert resp.status_code == 200, resp.text
    assert {row["status"] for row in resp.json()["data"]} == {"FAILED"}
