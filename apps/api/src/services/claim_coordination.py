from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..core.enums import PointsLedgerType
from ..core.errors import AppError
from ..core.models import Assignment, Lead, PointsLedger
from ..core.models_v12 import SupplierLeadReward
from ..core.security import decrypt_text
from .claim_fast_v12 import ClaimExecution, claim_assignment_fast
from .dispatch_v12 import CLAIMED_CONTACT_STATUSES, ClaimResult


_CROSS_WORKER_FOLLOWER_WAIT_SECONDS = 0.45
_POLL_DELAYS_SECONDS = (0.015, 0.025, 0.04, 0.06, 0.08, 0.10, 0.12)


@dataclass(frozen=True, slots=True)
class _ClaimProbe:
    assignment: Assignment
    lead: Lead
    ledger: PointsLedger | None
    reward: SupplierLeadReward | None


def claim_advisory_lock_key(assignment_id: str) -> int:
    """Return a deterministic signed bigint key for PostgreSQL advisory locks."""

    digest = hashlib.blake2b(
        assignment_id.encode("utf-8"),
        digest_size=8,
        person=b"zs-claim",
    ).digest()
    unsigned = int.from_bytes(digest, "big", signed=False)
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


def _claim_probe(db: Session, *, assignment_id: str, company_id: str) -> _ClaimProbe | None:
    """Read assignment, lead and idempotent claim facts in one READ COMMITTED statement."""

    row = db.execute(
        select(Assignment, Lead, PointsLedger, SupplierLeadReward)
        .join(Lead, Lead.id == Assignment.lead_id)
        .outerjoin(
            PointsLedger,
            and_(
                PointsLedger.company_id == company_id,
                PointsLedger.ledger_type == PointsLedgerType.CLAIM.value,
                PointsLedger.idempotency_key == f"v12-claim:{assignment_id}",
            ),
        )
        .outerjoin(SupplierLeadReward, SupplierLeadReward.assignment_id == Assignment.id)
        .where(Assignment.id == assignment_id)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if row is None:
        return None
    return _ClaimProbe(
        assignment=row[0],
        lead=row[1],
        ledger=row[2],
        reward=row[3],
    )


def _existing_claim_result(
    *,
    probe: _ClaimProbe,
    company_id: str,
) -> ClaimExecution | None:
    assignment = probe.assignment
    if assignment.company_id != company_id:
        raise AppError("ASSIGNMENT_FORBIDDEN", "无权领取其他公司的派发单", 403)
    if assignment.status not in CLAIMED_CONTACT_STATUSES:
        return None
    if probe.ledger is None:
        raise AppError("CLAIM_LEDGER_MISSING", "派发单已领取但积分流水缺失", 500)
    return ClaimExecution(
        result=ClaimResult(
            assignment=assignment,
            ledger=probe.ledger,
            reward=probe.reward,
            phone=decrypt_text(probe.lead.phone_encrypted),
            idempotent=True,
        ),
        lead=probe.lead,
    )


def _try_postgres_advisory_lock(db: Session, key: int) -> bool:
    return bool(db.scalar(select(func.pg_try_advisory_xact_lock(key))))


def _wait_for_postgres_advisory_lock(db: Session, key: int) -> None:
    db.execute(select(func.pg_advisory_xact_lock(key)))


def claim_assignment_coordinated(
    db: Session,
    *,
    assignment_id: str,
    company_id: str,
    claimed_by: str,
) -> ClaimExecution:
    """Claim with replay fast-path, worker coordination and a short transaction."""

    probe = _claim_probe(db, assignment_id=assignment_id, company_id=company_id)
    if probe is None:
        raise AppError("ASSIGNMENT_NOT_FOUND", "派发单不存在", 404)
    if probe.assignment.company_id != company_id:
        raise AppError("ASSIGNMENT_FORBIDDEN", "无权领取其他公司的派发单", 403)

    existing = _existing_claim_result(probe=probe, company_id=company_id)
    if existing is not None:
        return existing

    if db.get_bind().dialect.name != "postgresql":
        return claim_assignment_fast(
            db,
            assignment_id=assignment_id,
            company_id=company_id,
            claimed_by=claimed_by,
        )

    advisory_key = claim_advisory_lock_key(assignment_id)
    if _try_postgres_advisory_lock(db, advisory_key):
        db.expire_all()
        return claim_assignment_fast(
            db,
            assignment_id=assignment_id,
            company_id=company_id,
            claimed_by=claimed_by,
        )

    deadline = time.monotonic() + _CROSS_WORKER_FOLLOWER_WAIT_SECONDS
    for delay in _POLL_DELAYS_SECONDS:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(delay, remaining))
        probe = _claim_probe(db, assignment_id=assignment_id, company_id=company_id)
        if probe is None:
            raise AppError("ASSIGNMENT_NOT_FOUND", "派发单不存在", 404)
        existing = _existing_claim_result(probe=probe, company_id=company_id)
        if existing is not None:
            return existing

    # The exact database transaction remains authoritative. If the leader takes
    # longer than the follower budget, queue only one leader per worker on the
    # advisory lock rather than every replay request on the assignment row lock.
    _wait_for_postgres_advisory_lock(db, advisory_key)
    db.expire_all()
    return claim_assignment_fast(
        db,
        assignment_id=assignment_id,
        company_id=company_id,
        claimed_by=claimed_by,
    )
