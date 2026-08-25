#!/usr/bin/env python3
"""Export a read-only, de-identified snapshot before five-role migration."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core import models_v12 as _models_v12  # noqa: F401
from apps.api.src.core.database import SessionLocal
from apps.api.src.core.models import (
    Assignment,
    Company,
    CompanyCapability,
    CompanyServiceRegion,
    InviteToken,
    Lead,
    PointsAccount,
    PointsLedger,
    ReturnRequest,
    User,
)
from apps.api.src.core.models_v12 import SupplierLeadReward


SNAPSHOT_SCHEMA = "five-role-migration-snapshot.v1"
EXCLUDED_FIELDS = (
    "密码哈希、邀请令牌、邮箱、完整手机号、手机号哈希、客户姓名、需求描述、原始客资、"
    "派发快照、退回说明、积分幂等键、外部收款凭据和扩展元数据",
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _ordered(db: Session, model):
    return db.scalars(select(model).order_by(model.id)).all()


def build_snapshot(
    db: Session,
    *,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """Return only the migration/reconciliation fields needed for operator review."""

    captured_at = captured_at or datetime.now(timezone.utc)
    users = db.scalars(
        select(User).options(selectinload(User.roles)).order_by(User.id)
    ).all()
    companies = _ordered(db, Company)
    regions = _ordered(db, CompanyServiceRegion)
    capabilities = _ordered(db, CompanyCapability)
    invites = _ordered(db, InviteToken)
    accounts = _ordered(db, PointsAccount)
    ledgers = _ordered(db, PointsLedger)
    leads = _ordered(db, Lead)
    assignments = _ordered(db, Assignment)
    returns = _ordered(db, ReturnRequest)
    rewards = _ordered(db, SupplierLeadReward)

    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "captured_at": _iso(captured_at),
        "data_classification": "内部迁移核对资料；仅限授权迁移窗口使用",
        "excluded_fields": list(EXCLUDED_FIELDS),
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "status": user.status,
                "company_id": user.company_id,
                "session_version": user.session_version,
                "role_codes": sorted(role.code for role in user.roles),
                "last_login_at": _iso(user.last_login_at),
            }
            for user in users
        ],
        "companies": [
            {
                "id": company.id,
                "code": company.code,
                "name": company.name,
                "status": company.status,
                "level_code": company.level_code,
                "primary_user_id": company.primary_user_id,
                "created_at": _iso(company.created_at),
                "updated_at": _iso(company.updated_at),
            }
            for company in companies
        ],
        "company_service_regions": [
            {
                "id": region.id,
                "company_id": region.company_id,
                "region_code": region.region_code,
                "active": region.active,
                "created_at": _iso(region.created_at),
                "updated_at": _iso(region.updated_at),
            }
            for region in regions
        ],
        "company_capabilities": [
            {
                "id": capability.id,
                "company_id": capability.company_id,
                "category_code": capability.category_code,
                "brand_code": capability.brand_code,
                "active": capability.active,
                "created_at": _iso(capability.created_at),
                "updated_at": _iso(capability.updated_at),
            }
            for capability in capabilities
        ],
        "invites": [
            {
                "id": invite.id,
                "company_id": invite.company_id,
                "expires_at": _iso(invite.expires_at),
                "used_at": _iso(invite.used_at),
                "revoked_at": _iso(invite.revoked_at),
                "created_by": invite.created_by,
                "used_by_user_id": invite.used_by_user_id,
                "created_at": _iso(invite.created_at),
            }
            for invite in invites
        ],
        "points_accounts": [
            {
                "id": account.id,
                "company_id": account.company_id,
                "balance": account.balance,
                "version": account.version,
                "created_at": _iso(account.created_at),
                "updated_at": _iso(account.updated_at),
            }
            for account in accounts
        ],
        "points_ledgers": [
            {
                "id": ledger.id,
                "account_id": ledger.account_id,
                "company_id": ledger.company_id,
                "ledger_type": ledger.ledger_type,
                "delta": ledger.delta,
                "balance_after": ledger.balance_after,
                "business_type": ledger.business_type,
                "business_id": ledger.business_id,
                "related_ledger_id": ledger.related_ledger_id,
                "created_by": ledger.created_by,
                "created_at": _iso(ledger.created_at),
            }
            for ledger in ledgers
        ],
        "leads": [
            {
                "id": lead.id,
                "source_type": lead.source_type,
                "source_kind": lead.source_kind,
                "supplier_company_id": lead.supplier_company_id,
                "submitter_user_id": lead.submitter_user_id,
                "region_code": lead.region_code,
                "category_code": lead.category_code,
                "brand_code": lead.brand_code,
                "status": lead.status,
                "pending_reason": lead.pending_reason,
                "review_status": lead.review_status,
                "duplicate_status": lead.duplicate_status,
                "current_assignment_id": lead.current_assignment_id,
                "imported_at": _iso(lead.imported_at),
                "submitted_at": _iso(lead.submitted_at),
                "reviewed_at": _iso(lead.reviewed_at),
            }
            for lead in leads
        ],
        "assignments": [
            {
                "id": assignment.id,
                "lead_id": assignment.lead_id,
                "company_id": assignment.company_id,
                "supplier_company_id": assignment.supplier_company_id,
                "receiver_company_id": assignment.receiver_company_id,
                "status": assignment.status,
                "points_price": assignment.points_price,
                "claim_points": assignment.claim_points,
                "assigned_by": assignment.assigned_by,
                "internal_assignee_user_id": assignment.internal_assignee_user_id,
                "assigned_at": _iso(assignment.assigned_at),
                "claimed_at": _iso(assignment.claimed_at),
                "expires_at": _iso(assignment.expires_at),
                "released_at": _iso(assignment.released_at),
                "created_at": _iso(assignment.created_at),
                "updated_at": _iso(assignment.updated_at),
            }
            for assignment in assignments
        ],
        "returns": [
            {
                "id": request.id,
                "assignment_id": request.assignment_id,
                "lead_id": request.lead_id,
                "company_id": request.company_id,
                "reason_code": request.reason_code,
                "status": request.status,
                "submitted_by": request.submitted_by,
                "reviewed_by": request.reviewed_by,
                "refund_points": request.refund_points,
                "refund_ledger_id": request.refund_ledger_id,
                "verification_task_id": request.verification_task_id,
                "submitted_at": _iso(request.submitted_at),
                "reviewed_at": _iso(request.reviewed_at),
                "due_at": _iso(request.due_at),
                "created_at": _iso(request.created_at),
                "updated_at": _iso(request.updated_at),
            }
            for request in returns
        ],
        "rewards": [
            {
                "id": reward.id,
                "lead_id": reward.lead_id,
                "assignment_id": reward.assignment_id,
                "supplier_company_id": reward.supplier_company_id,
                "receiver_company_id": reward.receiver_company_id,
                "status": reward.status,
                "claim_points": reward.claim_points,
                "reward_points": reward.reward_points,
                "ledger_id": reward.ledger_id,
                "reversal_ledger_id": reward.reversal_ledger_id,
                "frozen_at": _iso(reward.frozen_at),
                "settled_at": _iso(reward.settled_at),
                "cancelled_at": _iso(reward.cancelled_at),
                "reversed_at": _iso(reward.reversed_at),
                "created_at": _iso(reward.created_at),
                "updated_at": _iso(reward.updated_at),
            }
            for reward in rewards
        ],
    }
    snapshot["counts"] = {
        "assignments": len(assignments),
        "companies": len(companies),
        "company_capabilities": len(capabilities),
        "company_service_regions": len(regions),
        "invites": len(invites),
        "leads": len(leads),
        "points_accounts": len(accounts),
        "points_ledgers": len(ledgers),
        "rewards": len(rewards),
        "returns": len(returns),
        "users": len(users),
    }
    return snapshot


def write_snapshot(
    snapshot: dict[str, object],
    output: Path,
    *,
    overwrite: bool = False,
) -> None:
    """Write atomically with owner-only permissions and no accidental overwrite."""

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise FileExistsError(f"快照文件已存在，拒绝覆盖：{output}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(snapshot, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary_path, output)
        else:
            os.link(temporary_path, output)
            temporary_path.unlink()
        os.chmod(output, 0o600)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出五角色迁移前的脱敏只读快照")
    parser.add_argument("--output", type=Path, required=True, help="快照 JSON 输出路径")
    parser.add_argument("--overwrite", action="store_true", help="明确覆盖同名旧快照")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        with session_factory() as db:
            snapshot = build_snapshot(db)
        write_snapshot(snapshot, args.output, overwrite=args.overwrite)
    except (OSError, SQLAlchemyError, ValueError) as exc:
        print(json.dumps({"status": "failed", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(args.output),
                "schema": SNAPSHOT_SCHEMA,
                "counts": snapshot["counts"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
