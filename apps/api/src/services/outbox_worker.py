from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.models import Company, Notification, NotificationOutbox, SystemConfig, WechatIdentity
from ..integrations.wechat import WechatOfficialAccountClient

settings = get_settings()


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
    sent = failed = dead = 0
    for item in rows:
        item.status = "PROCESSING"
        item.attempts += 1
        try:
            result = _send(db, client, item)
            if result["success"]:
                item.status, item.sent_at, item.last_error = "SENT", now, None
                sent += 1
            else:
                item.last_error = f"{result.get('error_code')}: {result.get('error_message')}"
                if item.attempts >= 5:
                    item.status = "DEAD"
                    dead += 1
                else:
                    item.status = "FAILED"
                    item.next_attempt_at = now + timedelta(minutes=min(60, 2**item.attempts))
                    failed += 1
        except Exception as exc:  # final delivery boundary
            item.last_error = str(exc)
            if item.attempts >= 5:
                item.status = "DEAD"
                dead += 1
            else:
                item.status = "FAILED"
                item.next_attempt_at = now + timedelta(minutes=min(60, 2**item.attempts))
                failed += 1
    return {"processed": len(rows), "sent": sent, "failed": failed, "dead": dead}


def _send(db: Session, client: WechatOfficialAccountClient, outbox: NotificationOutbox) -> dict[str, Any]:
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
        "V12_SUPPLIER_REWARD_OBSERVING": "客资奖励进入观察期", "V12_SUPPLIER_REWARD_FROZEN": "客资奖励已冻结",
        "V12_SUPPLIER_REWARD_SETTLED": "客资奖励已到账", "V12_SUPPLIER_REWARD_CANCELLED": "客资奖励已取消",
        "V12_SUPPLIER_REWARD_REVERSED": "客资奖励已冲正",
    }.get(event_type, "业务通知")
