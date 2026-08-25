from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.models import Company, Notification, NotificationOutbox, SystemConfig, WechatIdentity
from ..core.security import scrub_credentials
from ..integrations.wechat import WechatOfficialAccountClient

settings = get_settings()

# N7：确定性投递失败（模板未发布、邀请对象无 openid）重试不可能自愈——
# 直接终态化 MANUAL_ACTION_REQUIRED 交运营兜底，不空转 5 次退避重试污染
# 失败率；运营修好配置/收件人后经重试按钮手动重置 PENDING。
_MANUAL_ACTION_ERROR_CODES = frozenset({"TEMPLATE_NOT_CONFIGURED", "NO_RECIPIENT"})


def _template_for_scene(db: Session, scene: str) -> str | None:
    config = db.scalar(select(SystemConfig).where(
        SystemConfig.domain == "wechat_template",
        SystemConfig.key == scene,
        SystemConfig.status == "PUBLISHED",
    ).order_by(SystemConfig.version.desc()))
    return str(config.value_json.get("template_id")) if config and config.value_json.get("template_id") else None


def process_outbox(db: Session, limit: int = 100) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(NotificationOutbox).where(
        NotificationOutbox.status.in_(["PENDING", "FAILED"]),
        or_(NotificationOutbox.next_attempt_at.is_(None), NotificationOutbox.next_attempt_at <= now),
    ).order_by(NotificationOutbox.created_at).limit(limit)).all()
    client = WechatOfficialAccountClient()
    sent = failed = dead = manual = 0
    for item in rows:
        item.status = "PROCESSING"
        item.attempts += 1
        try:
            result = _send(db, client, item)
            if result["success"]:
                item.status, item.sent_at, item.last_error = "SENT", now, None
                sent += 1
            elif result.get("error_code") in _MANUAL_ACTION_ERROR_CODES:
                item.last_error = scrub_credentials(f"{result.get('error_code')}: {result.get('error_message')}")
                item.status = "MANUAL_ACTION_REQUIRED"
                item.next_attempt_at = None
                manual += 1
            else:
                item.last_error = scrub_credentials(f"{result.get('error_code')}: {result.get('error_message')}")
                if item.attempts >= 5:
                    item.status = "DEAD"
                    dead += 1
                else:
                    item.status = "FAILED"
                    item.next_attempt_at = now + timedelta(minutes=min(60, 2**item.attempts))
                    failed += 1
        except Exception as exc:  # final delivery boundary
            # N3：httpx 异常原文含完整微信 URL，access_token/secret 等参数即凭据；
            # 保留异常类名供排障，值一律打码并限长。
            item.last_error = f"{type(exc).__name__}: {scrub_credentials(str(exc))}"
            if item.attempts >= 5:
                item.status = "DEAD"
                dead += 1
            else:
                item.status = "FAILED"
                item.next_attempt_at = now + timedelta(minutes=min(60, 2**item.attempts))
                failed += 1
    return {"processed": len(rows), "sent": sent, "failed": failed, "dead": dead, "manual": manual}


def _send(db: Session, client: WechatOfficialAccountClient, outbox: NotificationOutbox) -> dict[str, Any]:
    # P2-03：邀请事件发生在负责人绑定微信之前——create_company_invite 拒绝已
    # 绑定公司，所以不存在可解析的主账号；走渠道投递分支而非通用收件人解析。
    if outbox.event_type == "INVITE_CREATED":
        return _send_invite_created(db, client, outbox)
    company_id = outbox.payload.get("company_id")
    user_id = outbox.payload.get("user_id")
    if not user_id and company_id:
        company = db.get(Company, company_id)
        user_id = company.primary_user_id if company else None
    if not user_id:
        return {"success": False, "error_code": "NO_RECIPIENT", "error_message": "未绑定微信负责人"}
    identity = db.scalar(select(WechatIdentity).where(WechatIdentity.user_id == user_id))
    if not identity:
        return {"success": False, "error_code": "NO_WECHAT_IDENTITY", "error_message": "未绑定微信身份"}

    notification = None
    notification_id = outbox.payload.get("notification_id")
    if notification_id:
        notification = db.get(Notification, str(notification_id))
    if notification is None:
        notification = db.scalar(select(Notification).where(
            or_(
                Notification.user_id == user_id,
                (Notification.user_id.is_(None)) & (Notification.company_id == company_id),
            ),
            Notification.scene == _scene_from_event(outbox.event_type),
        ).order_by(Notification.created_at.desc()))

    title = notification.title if notification else _default_title(outbox.event_type)
    body = notification.body if notification else "您有一条业务消息，请点击查看详情。"
    relative_url = notification.deep_link if notification and notification.deep_link else outbox.payload.get("deep_link", "/h5/")
    result = client.send_scene_message(
        openid=identity.openid,
        scene=outbox.event_type,
        title=title,
        body=body,
        url=settings.app_base_url.rstrip("/") + relative_url,
        template_id=_template_for_scene(db, outbox.event_type),
    )
    if notification:
        notification.status = "SENT" if result.success else "FAILED"
    return {"success": result.success, "message_id": result.message_id, "error_code": result.error_code, "error_message": result.error_message}


def _send_invite_created(db: Session, client: WechatOfficialAccountClient, outbox: NotificationOutbox) -> dict[str, Any]:
    """P2-03 channel delivery for invite events (recipient not bound yet).

    dev mock renders the template message and succeeds; the real channel
    fails with TEMPLATE_NOT_CONFIGURED until a template_id is published via
    SystemConfig(wechat_template/INVITE_CREATED) — that FAILED row is the
    honest "channel pending" signal, and manual sending remains the fallback.
    The outbox payload never carries the raw invite token.
    """

    payload = outbox.payload
    invitee = str(payload.get("invitee_name") or "负责人")
    company_name = str(payload.get("company_name") or "加盟商")
    expires_at = str(payload.get("expires_at") or "")
    template_id = _template_for_scene(db, outbox.event_type)
    # S1：真实通道下收件人仍是占位符——发起 API 只会得到非法 openid 错误并
    # 空转 5 次退避重试后落 DEAD；明确返回 NO_RECIPIENT，运营经创建弹窗人工
    # 发送兜底。未发布模板时仍走 TEMPLATE_NOT_CONFIGURED 的诚实失败。
    if not settings.wechat_dev_mock and template_id:
        return {
            "success": False,
            "error_code": "NO_RECIPIENT",
            "error_message": "邀请对象尚未绑定微信，请运营经创建弹窗手动发送",
        }
    result = client.send_scene_message(
        openid="channel-pending-bind",
        scene=outbox.event_type,
        title=f"微信绑定邀请已生成（{company_name}）",
        body=f"{invitee}的绑定邀请已生成，有效期至 {expires_at[:16].replace('T', ' ')}。请运营通过创建弹窗发送邀请链接。",
        url=settings.app_base_url.rstrip("/") + str(payload.get("deep_link", "/h5/#/login")),
        template_id=template_id,
    )
    return {"success": result.success, "message_id": result.message_id, "error_code": result.error_code, "error_message": result.error_message}


def _scene_from_event(event_type: str) -> str:
    return {
        "ASSIGNMENT_DISPATCHED": "NEW_LEAD", "ASSIGNMENT_REMINDER": "CLAIM_REMINDER",
        "ASSIGNMENT_CLAIMED": "CLAIM_SUCCESS", "FOLLOWUP_OVERDUE": "FOLLOWUP_OVERDUE",
        "RETURN_SUBMITTED": "RETURN_SUBMITTED", "RETURN_APPROVED": "RETURN_APPROVED",
        "RETURN_REJECTED": "RETURN_REJECTED", "RETURN_NEED_MORE": "RETURN_NEED_MORE",
        "POINTS_LOW_BALANCE": "LOW_POINTS", "POINTS_RECHARGED": "POINTS_RECHARGED",
    }.get(event_type, event_type)


def _default_title(event_type: str) -> str:
    return {
        "ASSIGNMENT_DISPATCHED": "新客资已派发", "ASSIGNMENT_REMINDER": "客资即将过期",
        "ASSIGNMENT_CLAIMED": "领取成功", "FOLLOWUP_OVERDUE": "跟进提醒",
        "RETURN_APPROVED": "退回审核通过", "RETURN_REJECTED": "退回审核未通过",
        "POINTS_LOW_BALANCE": "积分余额不足提醒", "POINTS_RECHARGED": "积分充值到账",
        "V12_SUPPLIER_LEAD_SUBMITTED": "客资已提交初审", "V12_SUPPLIER_LEAD_APPROVED": "客资初审已通过",
        "V12_SUPPLIER_LEAD_REJECTED": "客资初审未通过", "V12_ASSIGNMENT_DISPATCHED": "新客资已派发",
        "V12_ASSIGNMENT_CLAIMED": "客资领取成功", "V12_RETURN_SUBMITTED": "退回申诉已提交",
        "V12_RETURN_APPROVED": "退回申诉终审通过", "V12_RETURN_REJECTED": "退回申诉终审未通过",
        "V12_RETURN_NEED_MORE": "退回申诉需要补证",
        "V12_SUPPLIER_REWARD_OBSERVING": "客资奖励进入观察期", "V12_SUPPLIER_REWARD_FROZEN": "客资奖励已冻结",
        "V12_SUPPLIER_REWARD_SETTLED": "客资奖励已到账", "V12_SUPPLIER_REWARD_CANCELLED": "客资奖励已取消",
        "V12_SUPPLIER_REWARD_REVERSED": "客资奖励已冲正",
    }.get(event_type, "业务通知")
