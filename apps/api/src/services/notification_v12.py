from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import Assignment, Lead, NotificationOutbox, ReturnRequest, Role, User
from ..core.models_v12 import SupplierLeadReward
from ..core.time import as_utc
from ..core.v12_enums import RewardStatus
from .notification_service import create_station_message, enqueue_outbox


def build_v12_deep_link(target: str, business_id: str, *, admin: bool = False) -> str:
    allowed = {
        "lead",
        "assignment",
        "return",
        "reward",
        "report",
        "audit",
        "notification",
        "review",
        "dispatch",
        "returns",
        "rewards",
    }
    normalized = target.strip().lower()
    if normalized not in allowed:
        normalized = "notification"
    root = "/admin/v12-operations.html" if admin else "/h5/v12-workbench.html"
    return f"{root}?{urlencode({'view': normalized, 'id': business_id})}"


def emit_business_notification(
    db: Session,
    *,
    event_key: str,
    event_type: str,
    company_id: str | None,
    title: str,
    body: str,
    target: str,
    business_id: str,
    business_ids: dict[str, str | None] | None = None,
    user_id: str | None = None,
    admin: bool = False,
) -> NotificationOutbox | None:
    """Create one in-app message and one transactional outbox row.

    `event_key` is the cross-channel idempotency key. Re-running a command,
    retrying a request, or projecting the same domain transition cannot create
    duplicate messages.
    """

    if not company_id and not user_id:
        return None
    existing = db.scalar(
        select(NotificationOutbox).where(NotificationOutbox.event_key == event_key)
    )
    if existing:
        return existing

    deep_link = build_v12_deep_link(target, business_id, admin=admin)
    notification = create_station_message(
        db,
        user_id=user_id,
        company_id=company_id,
        scene=event_type,
        title=title,
        body=body,
        deep_link=deep_link,
    )
    payload = {
        "notification_id": notification.id,
        "company_id": company_id,
        "user_id": user_id,
        "deep_link": deep_link,
        "business_ids": {
            key: value for key, value in (business_ids or {}).items() if value
        },
    }
    return enqueue_outbox(
        db,
        event_key=event_key,
        event_type=event_type,
        aggregate_type=target,
        aggregate_id=business_id,
        payload=payload,
    )


def emit_platform_role_notifications(
    db: Session,
    *,
    event_key: str,
    event_type: str,
    role_codes: set[str],
    title: str,
    body: str,
    target: str,
    business_id: str,
    business_ids: dict[str, str | None] | None = None,
) -> int:
    """Notify active platform staff individually so deep links are permission scoped."""

    users = db.scalars(
        select(User)
        .join(User.roles)
        .where(Role.code.in_(sorted(role_codes)), User.status == "ACTIVE")
        .distinct()
    ).all()
    emitted = 0
    for user in users:
        item = emit_business_notification(
            db,
            event_key=f"{event_key}:user:{user.id}",
            event_type=event_type,
            company_id=None,
            user_id=user.id,
            title=title,
            body=body,
            target=target,
            business_id=business_id,
            business_ids=business_ids,
            admin=True,
        )
        emitted += int(item is not None)
    return emitted


def _notify_reward_state(db: Session, reward: SupplierLeadReward) -> None:
    status = reward.status
    copies: dict[str, tuple[str, str, str]] = {
        RewardStatus.OBSERVING.value: (
            "V12_SUPPLIER_REWARD_OBSERVING",
            "客资奖励进入观察期",
            "客资已被领取，奖励进入 3 个工作日观察期。",
        ),
        RewardStatus.FROZEN.value: (
            "V12_SUPPLIER_REWARD_FROZEN",
            "客资奖励已冻结",
            "接收方已发起退回申诉，奖励将在终审完成前保持冻结。",
        ),
        RewardStatus.SETTLED.value: (
            "V12_SUPPLIER_REWARD_SETTLED",
            "客资奖励已到账",
            f"本次供应商奖励 {int(reward.reward_points)} 积分已结算。",
        ),
        RewardStatus.CANCELLED.value: (
            "V12_SUPPLIER_REWARD_CANCELLED",
            "客资奖励已取消",
            "退回申诉终审通过，本次供应商奖励已取消。",
        ),
        RewardStatus.REVERSED.value: (
            "V12_SUPPLIER_REWARD_REVERSED",
            "客资奖励已冲正",
            "该笔奖励因异常处理已冲正，请进入奖励详情查看原因。",
        ),
    }
    copy = copies.get(status)
    if not copy:
        return
    event_type, title, body = copy
    emit_business_notification(
        db,
        event_key=f"v12:reward:{reward.id}:{status.lower()}",
        event_type=event_type,
        company_id=reward.supplier_company_id,
        title=title,
        body=body,
        target="reward",
        business_id=reward.id,
        business_ids={
            "lead_id": reward.lead_id,
            "assignment_id": reward.assignment_id,
            "reward_id": reward.id,
        },
    )
    if status in {
        RewardStatus.FROZEN.value,
        RewardStatus.SETTLED.value,
        RewardStatus.CANCELLED.value,
        RewardStatus.REVERSED.value,
    }:
        emit_platform_role_notifications(
            db,
            event_key=f"v12:reward:{reward.id}:{status.lower()}:platform",
            event_type=event_type,
            role_codes={"FINANCE", "OWNER", "SUPER_ADMIN"},
            title=title,
            body=body,
            target="rewards",
            business_id=reward.id,
            business_ids={
                "lead_id": reward.lead_id,
                "assignment_id": reward.assignment_id,
                "reward_id": reward.id,
            },
        )


def project_v12_notifications(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    company_id: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> None:
    """Project audited V1.2 state changes into notification/outbox records."""

    if not action.startswith("V12_") or not resource_id:
        return
    after = after or {}
    metadata = metadata or {}

    if action == "V12_SUPPLIER_LEAD_SUBMIT":
        lead = db.get(Lead, resource_id)
        if lead and lead.supplier_company_id:
            emit_business_notification(
                db,
                event_key=f"v12:lead:{lead.id}:submitted",
                event_type="V12_SUPPLIER_LEAD_SUBMITTED",
                company_id=lead.supplier_company_id,
                title="客资已提交初审",
                body="平台已收到客资资料，审核结果会通过消息通知。",
                target="lead",
                business_id=lead.id,
                business_ids={"lead_id": lead.id},
            )
            emit_platform_role_notifications(
                db,
                event_key=f"v12:lead:{lead.id}:submitted:platform",
                event_type="V12_SUPPLIER_LEAD_REVIEW_REQUIRED",
                role_codes={"OPERATION", "SUPER_ADMIN"},
                title="有新的供应商客资待初审",
                body="请核对资料完整性、客户授权和去重结果。",
                target="review",
                business_id=lead.id,
                business_ids={"lead_id": lead.id},
            )
        return

    if action == "V12_SUPPLIER_LEAD_REVIEW":
        lead = db.get(Lead, resource_id)
        if lead and lead.supplier_company_id:
            approved = str(lead.review_status or "").upper() == "APPROVED"
            event_type = (
                "V12_SUPPLIER_LEAD_APPROVED"
                if approved
                else "V12_SUPPLIER_LEAD_REJECTED"
            )
            emit_business_notification(
                db,
                event_key=f"v12:lead:{lead.id}:review:{str(lead.review_status).lower()}",
                event_type=event_type,
                company_id=lead.supplier_company_id,
                title="客资初审已通过" if approved else "客资初审未通过",
                body=(
                    "客资已进入待人工派发池。"
                    if approved
                    else "请进入客资详情查看平台说明并补充资料。"
                ),
                target="lead",
                business_id=lead.id,
                business_ids={"lead_id": lead.id},
            )
            if approved:
                emit_platform_role_notifications(
                    db,
                    event_key=f"v12:lead:{lead.id}:ready-dispatch:platform",
                    event_type="V12_LEAD_DISPATCH_REQUIRED",
                    role_codes={"OPERATION", "SUPER_ADMIN"},
                    title="客资初审通过，等待人工派发",
                    body="请进入待派发池选择符合区域、能力、去重和积分条件的接收公司。",
                    target="dispatch",
                    business_id=lead.id,
                    business_ids={"lead_id": lead.id},
                )
        return

    if action == "V12_MANUAL_DISPATCH":
        assignment = db.get(Assignment, resource_id)
        if assignment:
            receiver_company_id = assignment.receiver_company_id or assignment.company_id
            emit_business_notification(
                db,
                event_key=f"v12:assignment:{assignment.id}:dispatched",
                event_type="V12_ASSIGNMENT_DISPATCHED",
                company_id=receiver_company_id,
                title="新客资已派发",
                body="您有一条新的客资待领取，请在有效期内处理。",
                target="assignment",
                business_id=assignment.id,
                business_ids={
                    "lead_id": assignment.lead_id,
                    "assignment_id": assignment.id,
                },
            )
        return

    if action == "V12_ASSIGNMENT_CLAIM":
        assignment = db.get(Assignment, resource_id)
        if assignment:
            receiver_company_id = assignment.receiver_company_id or assignment.company_id
            emit_business_notification(
                db,
                event_key=f"v12:assignment:{assignment.id}:claimed",
                event_type="V12_ASSIGNMENT_CLAIMED",
                company_id=receiver_company_id,
                title="客资领取成功",
                body="客户联系方式已解锁，请按跟进时限完成首次联系。",
                target="assignment",
                business_id=assignment.id,
                business_ids={
                    "lead_id": assignment.lead_id,
                    "assignment_id": assignment.id,
                },
            )
            reward = db.scalar(
                select(SupplierLeadReward).where(
                    SupplierLeadReward.assignment_id == assignment.id
                )
            )
            if reward:
                _notify_reward_state(db, reward)
        return

    if action == "V12_RETURN_SUBMIT":
        request = db.get(ReturnRequest, resource_id)
        if request:
            emit_business_notification(
                db,
                event_key=f"v12:return:{request.id}:submitted",
                event_type="V12_RETURN_SUBMITTED",
                company_id=request.company_id,
                title="退回申诉已提交",
                body="申诉已进入后置电销核验，终审结果将通过消息通知。",
                target="return",
                business_id=request.id,
                business_ids={
                    "lead_id": request.lead_id,
                    "assignment_id": request.assignment_id,
                    "return_id": request.id,
                },
            )
            emit_platform_role_notifications(
                db,
                event_key=f"v12:return:{request.id}:verify-required:platform",
                event_type="V12_RETURN_VERIFY_REQUIRED",
                role_codes={"TELESALES", "OPERATION", "SUPER_ADMIN"},
                title="有新的退回申诉待后置核验",
                body="请领取或分配 RETURN_VERIFY 任务并完成事实核验。",
                target="returns",
                business_id=request.id,
                business_ids={
                    "lead_id": request.lead_id,
                    "assignment_id": request.assignment_id,
                    "return_id": request.id,
                },
            )
            reward = db.scalar(
                select(SupplierLeadReward).where(
                    SupplierLeadReward.assignment_id == request.assignment_id
                )
            )
            if reward:
                _notify_reward_state(db, reward)
        return

    if action == "V12_RETURN_VERIFY_SUBMIT":
        task_return_id = str(metadata.get("return_request_id") or "")
        request = db.get(ReturnRequest, task_return_id) if task_return_id else None
        if request is None:
            request = db.scalar(
                select(ReturnRequest).where(
                    ReturnRequest.verification_task_id == resource_id
                )
            )
        if request:
            emit_platform_role_notifications(
                db,
                event_key=f"v12:return:{request.id}:final-review-required:platform",
                event_type="V12_RETURN_FINAL_REVIEW_REQUIRED",
                role_codes={"RETURN_REVIEWER", "OPERATION", "SUPER_ADMIN"},
                title="退回事实核验已完成，等待终审",
                body="请结合申诉证据和电销核验结论完成平台终审。",
                target="returns",
                business_id=request.id,
                business_ids={
                    "lead_id": request.lead_id,
                    "assignment_id": request.assignment_id,
                    "return_id": request.id,
                    "verification_task_id": resource_id,
                },
            )
        return

    if action == "V12_RETURN_FINAL_REVIEW":
        request = db.get(ReturnRequest, resource_id)
        if request:
            approved = str(request.status).upper() == "APPROVED"
            emit_business_notification(
                db,
                event_key=f"v12:return:{request.id}:final:{str(request.status).lower()}",
                event_type=(
                    "V12_RETURN_APPROVED" if approved else "V12_RETURN_REJECTED"
                ),
                company_id=request.company_id,
                title="退回申诉终审通过" if approved else "退回申诉终审未通过",
                body=(
                    "退回已生效，相关积分已按规则处理。"
                    if approved
                    else "客资继续有效，请按业务流程继续跟进。"
                ),
                target="return",
                business_id=request.id,
                business_ids={
                    "lead_id": request.lead_id,
                    "assignment_id": request.assignment_id,
                    "return_id": request.id,
                },
            )
            reward = db.scalar(
                select(SupplierLeadReward).where(
                    SupplierLeadReward.assignment_id == request.assignment_id
                )
            )
            if reward:
                _notify_reward_state(db, reward)
        return

    if action in {
        "V12_SUPPLIER_REWARD_SETTLE",
        "V12_SUPPLIER_REWARD_REVERSE",
    }:
        reward = db.get(SupplierLeadReward, resource_id)
        if reward:
            _notify_reward_state(db, reward)


def drain_due_supplier_reward_settlement_notified(
    db: Session,
    *,
    as_of: datetime | None = None,
    batch_size: int = 500,
    max_batches: int = 20,
    settled_by: str | None = None,
) -> dict[str, Any]:
    """Run the bounded reward drain and project final reward states."""

    from .supplier_reward_v12 import drain_due_supplier_reward_settlement

    now = as_utc(as_of) or datetime.now(timezone.utc)
    safe_limit = max(1, min(int(batch_size), 1000)) * max(
        1, min(int(max_batches), 100)
    )
    candidate_ids = list(
        db.scalars(
            select(SupplierLeadReward.id)
            .where(
                SupplierLeadReward.status == RewardStatus.OBSERVING.value,
                SupplierLeadReward.reward_due_at.is_not(None),
                SupplierLeadReward.reward_due_at <= now,
            )
            .order_by(
                SupplierLeadReward.reward_due_at.asc(),
                SupplierLeadReward.id.asc(),
            )
            .limit(safe_limit)
        ).all()
    )
    result = drain_due_supplier_reward_settlement(
        db,
        as_of=now,
        batch_size=batch_size,
        max_batches=max_batches,
        settled_by=settled_by,
    )
    if candidate_ids:
        rewards = db.scalars(
            select(SupplierLeadReward).where(
                SupplierLeadReward.id.in_(candidate_ids)
            )
        ).all()
        for reward in rewards:
            if reward.status in {
                RewardStatus.FROZEN.value,
                RewardStatus.SETTLED.value,
            }:
                _notify_reward_state(db, reward)
    result["notification_candidates"] = len(candidate_ids)
    return result
