from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.models import Assignment, Lead, PointsAccount, PointsLedger, ReturnEvidence, ReturnRequest
from ..core.models_v12 import SupplierLeadReward, V12MigrationCheckpoint
from ..core.state_machine_v12 import LEGACY_LEAD_STATUS_MAP, LEGACY_RETURN_STATUS_MAP
from ..core.v12_enums import LeadV12Status, ReturnV12Status, RewardStatus
from .migration_v12 import PHONE_FINGERPRINT_CHECKPOINT

_ACTIVE_ASSIGNMENT_STATUSES = ("PENDING_CLAIM", "CLAIMED", "FOLLOWING", "RETURN_PENDING")


@dataclass(slots=True)
class ReconciliationReport:
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, **asdict(self)}


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "details": details}


def _count(db: Session, model: type, *criteria: Any) -> int:
    statement = select(func.count()).select_from(model)
    if criteria:
        statement = statement.where(*criteria)
    return int(db.scalar(statement) or 0)


def reconcile_v12(db: Session, *, require_completed_backfill: bool = True) -> ReconciliationReport:
    """Perform read-only release reconciliation without exposing PII."""

    report = ReconciliationReport()
    total_leads = _count(db, Lead)
    missing_fingerprints = _count(db, Lead, Lead.phone_fingerprint.is_(None))
    report.metrics.update(
        {
            "leads_total": total_leads,
            "leads_missing_phone_fingerprint": missing_fingerprints,
            "assignments_total": _count(db, Assignment),
            "returns_total": _count(db, ReturnRequest),
            "supplier_rewards_total": _count(db, SupplierLeadReward),
            "return_evidence_total": _count(db, ReturnEvidence),
        }
    )
    checkpoint = db.get(V12MigrationCheckpoint, PHONE_FINGERPRINT_CHECKPOINT)
    report.metrics["phone_fingerprint_checkpoint"] = (
        {
            "status": checkpoint.status,
            "processed_count": checkpoint.processed_count,
            "error_count": checkpoint.error_count,
            "cursor": checkpoint.cursor,
        }
        if checkpoint
        else None
    )
    if require_completed_backfill and missing_fingerprints:
        report.errors.append(
            _issue(
                "PHONE_FINGERPRINT_INCOMPLETE",
                "仍有客资未生成 V1.2 手机号指纹",
                count=missing_fingerprints,
            )
        )
    if checkpoint and checkpoint.status == "COMPLETED_WITH_ERRORS":
        report.errors.append(
            _issue(
                "PHONE_FINGERPRINT_ROW_ERRORS",
                "手机号指纹回填存在失败行",
                error_count=checkpoint.error_count,
            )
        )
    elif require_completed_backfill and total_leads and (
        checkpoint is None or checkpoint.status != "COMPLETED"
    ):
        report.errors.append(
            _issue(
                "PHONE_FINGERPRINT_CHECKPOINT_NOT_COMPLETE",
                "手机号指纹回填检查点未完成",
                status=checkpoint.status if checkpoint else None,
            )
        )

    duplicate_active = db.execute(
        select(Assignment.lead_id, func.count(Assignment.id))
        .where(Assignment.status.in_(_ACTIVE_ASSIGNMENT_STATUSES))
        .group_by(Assignment.lead_id)
        .having(func.count(Assignment.id) > 1)
        .limit(50)
    ).all()
    report.metrics["duplicate_active_assignment_leads"] = len(duplicate_active)
    if duplicate_active:
        report.errors.append(
            _issue(
                "DUPLICATE_ACTIVE_ASSIGNMENT",
                "同一客资存在多个有效派发单",
                samples=[{"lead_id": row[0], "count": int(row[1])} for row in duplicate_active],
            )
        )

    allowed_lead_statuses = {item.value for item in LeadV12Status} | set(LEGACY_LEAD_STATUS_MAP)
    lead_statuses = set(db.scalars(select(Lead.status).distinct()).all())
    unknown_lead_statuses = sorted(status for status in lead_statuses if status not in allowed_lead_statuses)
    report.metrics["unknown_lead_statuses"] = unknown_lead_statuses
    if unknown_lead_statuses:
        report.errors.append(
            _issue("UNKNOWN_LEAD_STATUS", "发现无法映射的历史客资状态", statuses=unknown_lead_statuses)
        )

    allowed_return_statuses = {item.value for item in ReturnV12Status} | set(LEGACY_RETURN_STATUS_MAP)
    return_statuses = set(db.scalars(select(ReturnRequest.status).distinct()).all())
    unknown_return_statuses = sorted(status for status in return_statuses if status not in allowed_return_statuses)
    report.metrics["unknown_return_statuses"] = unknown_return_statuses
    if unknown_return_statuses:
        report.errors.append(
            _issue("UNKNOWN_RETURN_STATUS", "发现无法映射的历史退回状态", statuses=unknown_return_statuses)
        )

    account_mismatches: list[dict[str, Any]] = []
    accounts = list(db.scalars(select(PointsAccount).order_by(PointsAccount.company_id)).all())
    for account in accounts:
        ledger_sum = int(
            db.scalar(
                select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(
                    PointsLedger.account_id == account.id
                )
            )
            or 0
        )
        latest_balance = db.scalar(
            select(PointsLedger.balance_after)
            .where(PointsLedger.account_id == account.id)
            .order_by(PointsLedger.created_at.desc(), PointsLedger.id.desc())
            .limit(1)
        )
        if ledger_sum != account.balance or (
            latest_balance is not None and int(latest_balance) != account.balance
        ):
            account_mismatches.append(
                {
                    "company_id": account.company_id,
                    "account_balance": int(account.balance),
                    "ledger_sum": ledger_sum,
                    "latest_balance_after": int(latest_balance) if latest_balance is not None else None,
                }
            )
    report.metrics["points_accounts_total"] = len(accounts)
    report.metrics["points_account_mismatches"] = len(account_mismatches)
    if account_mismatches:
        report.errors.append(
            _issue(
                "POINTS_RECONCILIATION_MISMATCH",
                "积分账户与不可变流水不一致",
                samples=account_mismatches[:50],
            )
        )

    settled_without_ledger = _count(
        db,
        SupplierLeadReward,
        SupplierLeadReward.status == RewardStatus.SETTLED.value,
        SupplierLeadReward.ledger_id.is_(None),
    )
    reversed_without_ledger = _count(
        db,
        SupplierLeadReward,
        SupplierLeadReward.status == RewardStatus.REVERSED.value,
        SupplierLeadReward.reversal_ledger_id.is_(None),
    )
    approved_without_refund = _count(
        db,
        ReturnRequest,
        ReturnRequest.status == ReturnV12Status.APPROVED.value,
        ReturnRequest.refund_ledger_id.is_(None),
    )
    evidence_invalid = _count(
        db,
        ReturnEvidence,
        (ReturnEvidence.object_key == "") | (ReturnEvidence.sha256 == "") | (ReturnEvidence.file_size <= 0),
    )
    report.metrics.update(
        {
            "settled_rewards_without_ledger": settled_without_ledger,
            "reversed_rewards_without_ledger": reversed_without_ledger,
            "approved_returns_without_refund_ledger": approved_without_refund,
            "invalid_evidence_records": evidence_invalid,
        }
    )
    for code, message, count in (
        ("SETTLED_REWARD_LEDGER_MISSING", "已结算奖励缺少积分流水", settled_without_ledger),
        ("REVERSED_REWARD_LEDGER_MISSING", "已冲正奖励缺少反向流水", reversed_without_ledger),
        ("APPROVED_RETURN_REFUND_MISSING", "已通过退回缺少返分流水", approved_without_refund),
        ("INVALID_EVIDENCE_METADATA", "退回证据元数据不完整", evidence_invalid),
    ):
        if count:
            report.errors.append(_issue(code, message, count=count))

    if not accounts:
        report.warnings.append(_issue("NO_POINTS_ACCOUNTS", "当前数据库没有积分账户"))
    if not total_leads:
        report.warnings.append(_issue("NO_LEADS", "当前数据库没有客资，无法完成生产数据抽样"))
    return report
