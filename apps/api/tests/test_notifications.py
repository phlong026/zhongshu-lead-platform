import json

from sqlalchemy import select

import apps.api.src.integrations.wechat as wechat_module
from apps.api.src.core.models import (
    Company,
    Notification,
    NotificationOutbox,
    SystemConfig,
    User,
    WechatIdentity,
)
from apps.api.src.integrations.wechat import WechatOfficialAccountClient, WechatSendResult
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.company_service import create_company
from apps.api.src.services.notification_service import create_station_message, enqueue_outbox
from apps.api.src.services.outbox_worker import _default_title, process_outbox
# I19/N13：admin 登录头与 test_auth_company 单一来源，不再手写样板。
from test_auth_company import _admin_headers


def test_notification_list_returns_total_unread_independent_of_current_page(api_client) -> None:
    client, factory = api_client
    headers = _admin_headers(client)

    with factory() as db:
        actor = db.scalar(select(User).where(User.username == "admin"))
        assert actor is not None
        db.add_all(
            [
                Notification(
                    user_id=actor.id,
                    company_id=None,
                    scene=f"TEST_UNREAD_{index}",
                    title=f"未读消息 {index}",
                    body="用于验证分页外总未读数",
                    deep_link=None,
                    status="CREATED",
                )
                for index in range(3)
            ]
        )
        db.commit()

    response = client.get("/api/v1/notifications?page=1&page_size=1", headers=headers)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["items"]) == 1
    assert data["unread_total"] >= 3


def test_publish_wechat_template_config_rejects_invalid_field_map(api_client) -> None:
    client, _factory = api_client
    headers = _admin_headers(client)

    response = client.post(
        "/api/v1/system-configs",
        headers=headers,
        json={
            "domain": "wechat_template",
            "key": "V12_ASSIGNMENT_DISPATCHED",
            "value": {
                "template_id": "tmpl-test",
                "field_map": {"thing1": "unsupported_source"},
            },
            "publish_immediately": True,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "WECHAT_TEMPLATE_CONFIG_INVALID"


def test_outbox_default_title_keeps_v12_copy_in_config_not_worker_fallback() -> None:
    assert _default_title("V12_ASSIGNMENT_DISPATCHED") == "业务通知"


def test_same_company_same_scene_outbox_uses_its_own_notification(
    db,
    monkeypatch,
) -> None:
    company = Company(code="NOTIFY-BIND", name="通知精确绑定测试公司")
    db.add(company)
    db.flush()
    owner = User(display_name="通知负责人", company_id=company.id)
    db.add(owner)
    db.flush()
    company.primary_user_id = owner.id
    db.add(WechatIdentity(openid="o-notification-binding", user_id=owner.id))
    first_notification = create_station_message(
        db,
        user_id=None,
        company_id=company.id,
        scene="V12_CORRECTION_REDISPATCH",
        title="第一条撤回",
        body="第一条客资退回 100 积分",
        deep_link="/h5/v12-workbench.html?view=assignments&id=assignment-1",
    )
    second_notification = create_station_message(
        db,
        user_id=None,
        company_id=company.id,
        scene="V12_CORRECTION_REDISPATCH",
        title="第二条撤回",
        body="第二条客资退回 200 积分",
        deep_link="/h5/v12-workbench.html?view=assignments&id=assignment-2",
    )
    for index, notification in enumerate(
        (first_notification, second_notification),
        start=1,
    ):
        enqueue_outbox(
            db,
            event_key=f"test:correction-redispatch:{index}",
            event_type="V12_CORRECTION_REDISPATCH",
            aggregate_type="assignment",
            aggregate_id=f"assignment-{index}",
            payload={
                "company_id": company.id,
                "notification_id": notification.id,
                "deep_link": notification.deep_link,
            },
        )
    db.commit()
    sent: list[tuple[str, str, str | None]] = []

    def capture_message(
        _client,
        *,
        title: str,
        body: str,
        url: str | None,
        **_kwargs,
    ) -> WechatSendResult:
        sent.append((title, body, url))
        return WechatSendResult(success=True, message_id=f"sent-{len(sent)}")

    monkeypatch.setattr(
        WechatOfficialAccountClient,
        "send_scene_message",
        capture_message,
    )

    result = process_outbox(db)

    assert result["sent"] == 2
    assert sent == [
        (
            "第一条撤回",
            "第一条客资退回 100 积分",
            wechat_module.settings.app_base_url.rstrip("/")
            + first_notification.deep_link,
        ),
        (
            "第二条撤回",
            "第二条客资退回 200 积分",
            wechat_module.settings.app_base_url.rstrip("/")
            + second_notification.deep_link,
        ),
    ]


def test_publishing_draft_wechat_template_revalidates_empty_literal(api_client) -> None:
    client, _factory = api_client
    headers = _admin_headers(client)
    draft = client.post(
        "/api/v1/system-configs",
        headers=headers,
        json={
            "domain": "wechat_template",
            "key": "V12_ASSIGNMENT_DISPATCHED",
            "value": {
                "template_id": "tmpl-test",
                "field_map": {"thing1": "literal:   "},
            },
            "publish_immediately": False,
        },
    )
    assert draft.status_code == 200, draft.text

    response = client.post(
        f"/api/v1/system-configs/{draft.json()['data']['id']}/publish",
        headers=headers,
        json={},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "WECHAT_TEMPLATE_CONFIG_INVALID"


def test_official_account_client_uses_configured_template_field_map(monkeypatch) -> None:
    """公众号模板字段由已发布配置决定，避免模板关键字名称不一致时盲发。"""

    from apps.api.src.integrations.wechat import WechatOfficialAccountClient

    class _Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, int]:
            return {"errcode": 0, "msgid": 123}

    sent: dict[str, object] = {}

    def fake_post(url: str, *, json: dict[str, object], timeout: int):
        sent.update({"url": url, "json": json, "timeout": timeout})
        return _Response()

    monkeypatch.setattr(wechat_module.settings, "wechat_dev_mock", False)
    monkeypatch.setattr(wechat_module.httpx, "post", fake_post)
    client = WechatOfficialAccountClient()
    client._access_token = "test-access-token"
    client._expires_at = (
        wechat_module.datetime.now(wechat_module.timezone.utc)
        + wechat_module.timedelta(hours=1)
    )

    result = client.send_scene_message(
        openid="o-test-user",
        scene="V12_ASSIGNMENT_DISPATCHED",
        title="新客资已派发",
        body="上海市浦东新区，领取截止 18:00",
        url="https://zszhj.cn/h5/#/leads",
        template_id="approved-template-id",
        field_map={
            "first": "title",
            "keyword1": "scene",
            "keyword2": "body",
            "remark": "remark",
        },
    )

    assert result.success is True
    assert sent["json"] == {
        "touser": "o-test-user",
        "template_id": "approved-template-id",
        "url": "https://zszhj.cn/h5/#/leads",
        "data": {
            "first": {"value": "新客资已派发"},
            "keyword1": {"value": "V12_ASSIGNMENT_DISPATCHED"},
            "keyword2": {"value": "上海市浦东新区，领取截止 18:00"},
            "remark": {"value": "点击查看详情"},
        },
    }


def test_official_account_client_sends_v12_dispatch_template(monkeypatch) -> None:
    """新客资派发必须使用已核验的模板 ID 与字段键，避免升级时静默错配。"""

    from apps.api.src.integrations.wechat import WechatOfficialAccountClient

    class _Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, int]:
            return {"errcode": 0, "msgid": 124}

    sent: dict[str, object] = {}

    def fake_post(url: str, *, json: dict[str, object], timeout: int):
        sent["json"] = json
        return _Response()

    monkeypatch.setattr(wechat_module.settings, "wechat_dev_mock", False)
    monkeypatch.setattr(wechat_module.httpx, "post", fake_post)
    client = WechatOfficialAccountClient()
    client._access_token = "test-access-token"
    client._expires_at = (
        wechat_module.datetime.now(wechat_module.timezone.utc)
        + wechat_module.timedelta(hours=1)
    )

    result = client.send_scene_message(
        openid="o-test-user",
        scene="V12_ASSIGNMENT_DISPATCHED",
        title="您有一条新客资待领取",
        body="上海·浦东｜旧改客资",
        url="https://zszhj.cn/h5/#/leads",
        template_id="lY0K9b-7pB0bOnfjOJ6zPvPeL5fm0DjPhjxhRUZt3MU",
        field_map={"thing1": "title", "const16": "literal:乡墅新客资"},
    )

    assert result.success is True
    assert sent["json"] == {
        "touser": "o-test-user",
        "template_id": "lY0K9b-7pB0bOnfjOJ6zPvPeL5fm0DjPhjxhRUZt3MU",
        "url": "https://zszhj.cn/h5/#/leads",
        "data": {
            "thing1": {"value": "您有一条新客资待领取"},
            "const16": {"value": "乡墅新客资"},
        },
    }


def test_official_account_client_rejects_unknown_template_field_source(monkeypatch) -> None:
    from apps.api.src.integrations.wechat import WechatOfficialAccountClient

    monkeypatch.setattr(wechat_module.settings, "wechat_dev_mock", False)
    result = WechatOfficialAccountClient().send_scene_message(
        openid="o-test-user",
        scene="V12_ASSIGNMENT_DISPATCHED",
        title="新客资已派发",
        body="测试内容",
        url="https://zszhj.cn/h5/#/leads",
        template_id="approved-template-id",
        field_map={"keyword1": "unsupported_source"},
    )

    assert result.success is False
    assert result.error_code == "TEMPLATE_CONFIG_INVALID"


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
        assert item.payload["deep_link"] == "/h5/invite.html"
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


def test_outbox_invalid_template_field_map_requires_manual_action(db, monkeypatch) -> None:
    """字段映射填错是确定性配置错误，不能消耗重试次数。"""

    from apps.api.src.core.models import User, WechatIdentity

    monkeypatch.setattr(wechat_module.settings, "wechat_dev_mock", False)
    user = User(display_name="模板测试负责人", status="ACTIVE")
    db.add(user)
    db.flush()
    db.add(WechatIdentity(openid="o-template-config", user_id=user.id))
    db.add(
        SystemConfig(
            domain="wechat_template",
            key="ASSIGNMENT_DISPATCHED",
            status="PUBLISHED",
            value_json={"template_id": "approved-template-id", "field_map": {"keyword1": "unknown"}},
        )
    )
    item = enqueue_outbox(
        db,
        event_key="test:invalid-template-map",
        event_type="ASSIGNMENT_DISPATCHED",
        aggregate_type="assignment",
        aggregate_id="a-template-map",
        payload={"user_id": user.id},
    )
    db.commit()

    result = process_outbox(db)
    db.commit()

    assert result["manual"] == 1
    assert item.status == "MANUAL_ACTION_REQUIRED"
    assert "TEMPLATE_CONFIG_INVALID" in (item.last_error or "")


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


def test_operation_cannot_review_or_retry_failed_outbox(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        create_internal_user(
            db,
            username="notification-operation",
            password="Operation123!",
            display_name="通知运营",
            role_code="OPERATION",
        )
        db.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "notification-operation", "password": "Operation123!"},
    )
    assert login.status_code == 200, login.text
    token = login.cookies.get("access_token")
    assert token
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/notifications/outbox/failed", headers=headers).status_code == 403
    assert client.post("/api/v1/notifications/outbox/not-a-real-id/retry", headers=headers).status_code == 403
