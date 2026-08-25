#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from apps.api.src.core.enums import AssignmentStatus, PointsLedgerType
from apps.api.src.core.config import get_settings
from apps.api.src.core.models import Assignment, Company, Lead, PointsAccount, PointsLedger, ReturnRequest, User
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_password, hash_phone
from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status, ReturnV12Status
from apps.api.src.services.rbac import assign_role
from scripts.performance_v12 import DEFAULT_PROFILES, safe_origin, validate_claim_baseline, validate_dataset


DATASET_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{2,27}")
DEFAULT_REGION_CODE = "310104"
DEFAULT_POINTS_PRICE = 100
DEFAULT_INITIAL_POINTS = 1_000_000
DATABASE_ENVIRONMENT_SETTING = "zhongshu.environment_classification"
STAGING_DATABASE_MARKER = "staging-performance"
_DEVELOPMENT_SECRETS = {
    "FIELD_ENCRYPTION_KEY": "dev-only-key-change-in-production",
    "PHONE_HASH_SECRET": "dev-phone-hash-secret",
    "PHONE_FINGERPRINT_SECRET": "",
}


@dataclass(frozen=True)
class DatasetCredentials:
    operator_username: str
    operator_password: str
    receiver_username: str
    receiver_password: str
    owner_username: str
    owner_password: str


def _stable_id(dataset_id: str, resource: str, index: int | None = None) -> str:
    suffix = resource if index is None else f"{resource}:{index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"zhongshu:h04:{dataset_id}:{suffix}"))


def _password() -> str:
    return f"H04!{secrets.token_urlsafe(24)}"


def credentials_for(dataset_id: str) -> DatasetCredentials:
    prefix = f"h04_{dataset_id.replace('-', '_')}"
    return DatasetCredentials(
        operator_username=f"{prefix}_operation",
        operator_password=_password(),
        receiver_username=f"{prefix}_receiver",
        receiver_password=_password(),
        owner_username=f"{prefix}_owner",
        owner_password=_password(),
    )


def _validate_inputs(dataset_id: str, profiles: tuple[int, ...], initial_points: int) -> None:
    if not DATASET_ID_PATTERN.fullmatch(dataset_id):
        raise ValueError("dataset id must be 3-28 lowercase letters, digits, or hyphens")
    if not profiles or len(set(profiles)) != len(profiles) or any(profile <= 0 or profile > 1000 for profile in profiles):
        raise ValueError("profiles must be unique integers between 1 and 1000")
    # Evidence fixtures already carry a claim debit. During the ordered run,
    # every completed claim consumes one more debit while each completed
    # dispatch leaves another pending reservation. The final profile therefore
    # needs two profile-counts of headroom above the evidence debits.
    required_points = (sum(profiles) + 2 * len(profiles)) * DEFAULT_POINTS_PRICE
    if initial_points < required_points:
        raise ValueError(f"initial points must be at least {required_points}")


def validate_database_target(
    *,
    app_env: str,
    current_database: str,
    expected_database: str,
    database_environment: str,
) -> None:
    if app_env.strip().lower() != "staging":
        raise ValueError("synthetic capacity data requires APP_ENV=staging")
    if not expected_database.strip() or current_database != expected_database.strip():
        raise ValueError(
            f"connected database {current_database!r} does not match the explicit expected database name"
        )
    if database_environment != STAGING_DATABASE_MARKER:
        raise ValueError(
            f"database must declare {DATABASE_ENVIRONMENT_SETTING}={STAGING_DATABASE_MARKER!r}"
        )


def validate_runtime_secrets(
    *,
    field_encryption_key: str,
    phone_hash_secret: str,
    phone_fingerprint_secret: str,
) -> None:
    values = {
        "FIELD_ENCRYPTION_KEY": field_encryption_key.strip(),
        "PHONE_HASH_SECRET": phone_hash_secret.strip(),
        "PHONE_FINGERPRINT_SECRET": phone_fingerprint_secret.strip(),
    }
    for name, value in values.items():
        if value == _DEVELOPMENT_SECRETS[name] or value.lower().startswith("dev-") or len(value) < 32:
            raise ValueError(f"{name} must be an explicit non-development secret of at least 32 characters")
    if len(set(values.values())) != len(values):
        raise ValueError("capacity preparation requires three distinct runtime secrets")


def validate_credentials_storage(
    *,
    platform_name: str,
    credentials_path: Path | PurePosixPath,
    running_in_container: bool,
) -> None:
    if platform_name != "posix" or not running_in_container:
        raise ValueError(
            "credentials output requires a POSIX container with enforceable mode 0600; "
            "run the preparation command inside the staging API container"
        )
    candidate = PurePosixPath(str(credentials_path))
    temporary_root = PurePosixPath("/tmp")
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("credentials output must be an absolute path below /tmp")
    try:
        candidate.relative_to(temporary_root)
    except ValueError as exc:
        raise ValueError("credentials output must be an absolute path below /tmp") from exc
    if os.name == "posix":
        resolved_root = Path(temporary_root).resolve(strict=True)
        resolved_candidate = Path(credentials_path).resolve(strict=False)
        if not resolved_candidate.is_relative_to(resolved_root):
            raise ValueError("credentials output must remain below the real /tmp directory")


def _ensure_unused(db: Session, dataset_id: str, credentials: DatasetCredentials) -> None:
    source_token = f"h04:{dataset_id}"
    existing_leads = db.scalar(select(func.count(Lead.id)).where(Lead.source_app_token == source_token)) or 0
    company_code = f"H04-{dataset_id.upper()}"
    usernames = (
        credentials.operator_username,
        credentials.receiver_username,
        credentials.owner_username,
    )
    if existing_leads or db.scalar(select(Company.id).where(Company.code == company_code)):
        raise ValueError("dataset already exists; restore the pre-run snapshot or choose a new dataset id")
    if db.scalar(select(User.id).where(User.username.in_(usernames))):
        raise ValueError("one or more dedicated dataset usernames already exist")


def _user(
    db: Session,
    *,
    dataset_id: str,
    resource: str,
    username: str,
    password: str,
    role_code: str,
    company_id: str | None = None,
) -> User:
    user = User(
        id=_stable_id(dataset_id, resource),
        username=username,
        password_hash=hash_password(password),
        display_name=f"H04 synthetic {resource}",
        status="ACTIVE",
        company_id=company_id,
        session_version=1,
    )
    db.add(user)
    db.flush()
    assign_role(db, user, role_code)
    return user


def _lead(
    *,
    dataset_id: str,
    resource: str,
    index: int,
    submitter_user_id: str,
    status: str,
    now: datetime,
) -> Lead:
    synthetic_phone = f"000{index:08d}"[-11:]
    return Lead(
        id=_stable_id(dataset_id, f"lead-{resource}", index),
        source_type=LeadSourceKind.PLATFORM_MANUAL.value,
        source_kind=LeadSourceKind.PLATFORM_MANUAL.value,
        source_app_token=f"h04:{dataset_id}",
        source_table_id=resource,
        source_record_id=str(index),
        source_channel="H04_SYNTHETIC",
        submitter_user_id=submitter_user_id,
        supplier_company_id=None,
        customer_name=f"H04 synthetic customer {index}",
        phone_encrypted=encrypt_text(synthetic_phone),
        phone_hash=hash_phone(synthetic_phone),
        phone_fingerprint=fingerprint_phone(synthetic_phone),
        consent_confirmed=True,
        province="Synthetic",
        city="Synthetic",
        district="Synthetic",
        region_code=DEFAULT_REGION_CODE,
        category_code="OLD_RENOVATION",
        brand_code="ZHONGSHU",
        need_summary="H04 synthetic capacity fixture",
        status=status,
        review_status="APPROVED",
        duplicate_status="CLEAR",
        current_follow_status="UNCONTACTED" if status == LeadV12Status.CLAIMED.value else None,
        imported_at=now,
        submitted_at=now,
        verified_at=now,
        raw_payload={"synthetic_data": True, "dataset_id": dataset_id, "resource": resource},
    )


def prepare_dataset(
    db: Session,
    *,
    dataset_id: str,
    base_url_origin: str,
    environment: str,
    profiles: tuple[int, ...],
    credentials: DatasetCredentials,
    initial_points: int = DEFAULT_INITIAL_POINTS,
    claim_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_inputs(dataset_id, profiles, initial_points)
    validate_claim_baseline(claim_baseline)
    origin = safe_origin(base_url_origin)
    if environment not in {"staging", "staging-equivalent"}:
        raise ValueError("environment must be staging or staging-equivalent")
    _ensure_unused(db, dataset_id, credentials)

    now = datetime.now(timezone.utc)
    company = Company(
        id=_stable_id(dataset_id, "company"),
        code=f"H04-{dataset_id.upper()}",
        name=f"H04 synthetic receiver {dataset_id}",
        status="ACTIVE",
        level_code="V1",
        notes=f"Synthetic capacity tenant for {dataset_id}; restore the database snapshot after the run.",
    )
    db.add(company)
    db.flush()
    operator = _user(
        db,
        dataset_id=dataset_id,
        resource="operator",
        username=credentials.operator_username,
        password=credentials.operator_password,
        role_code="OPERATION",
    )
    receiver = _user(
        db,
        dataset_id=dataset_id,
        resource="receiver",
        username=credentials.receiver_username,
        password=credentials.receiver_password,
        role_code="FRANCHISE_OWNER",
        company_id=company.id,
    )
    owner = _user(
        db,
        dataset_id=dataset_id,
        resource="owner",
        username=credentials.owner_username,
        password=credentials.owner_password,
        # 压测中的 owner 仅用于平台级报表读取和积分种子审计；五角色模型中
        # 这属于超级管理员职责，不再保留历史 OWNER 角色。
        role_code="SUPER_ADMIN",
    )
    company.primary_user_id = receiver.id

    db.add_all(
        [
            CompanyLeadCapability(
                id=_stable_id(dataset_id, "receiver-capability"),
                company_id=company.id,
                capability_code="LEAD_RECEIVER",
                active=True,
                review_status="APPROVED",
                reviewed_by=operator.id,
                reviewed_at=now,
            ),
            CompanyServiceAreaV12(
                id=_stable_id(dataset_id, "receiver-service-area"),
                company_id=company.id,
                region_code=DEFAULT_REGION_CODE,
                region_level="DISTRICT",
                is_primary_city=True,
                active=True,
                review_status="APPROVED",
                reviewed_by=operator.id,
                reviewed_at=now,
                review_note="H04 synthetic capacity fixture",
            ),
        ]
    )

    account = PointsAccount(
        id=_stable_id(dataset_id, "points-account"),
        company_id=company.id,
        balance=initial_points,
        version=1,
    )
    db.add(account)
    db.flush()
    db.add(
        PointsLedger(
            id=_stable_id(dataset_id, "points-seed-ledger"),
            account_id=account.id,
            company_id=company.id,
            ledger_type=PointsLedgerType.ADJUST.value,
            delta=initial_points,
            balance_after=initial_points,
            business_type="H04_SYNTHETIC_SEED",
            business_id=dataset_id,
            idempotency_key=f"h04:{dataset_id}:points-seed",
            created_by=owner.id,
            metadata_json={"synthetic_data": True, "dataset_id": dataset_id},
            created_at=now,
        )
    )

    dispatch_cases: dict[str, dict[str, str]] = {}
    claim_cases: dict[str, str] = {}
    evidence_cases: dict[str, list[str]] = {}
    sequence = 1

    for profile in profiles:
        lead = _lead(
            dataset_id=dataset_id,
            resource=f"dispatch-{profile}",
            index=sequence,
            submitter_user_id=operator.id,
            status=LeadV12Status.READY_DISPATCH.value,
            now=now,
        )
        db.add(lead)
        dispatch_cases[str(profile)] = {
            "lead_id": lead.id,
            "idempotency_key": f"h04:{dataset_id}:dispatch:{profile}",
        }
        sequence += 1

    claim_assignments: list[Assignment] = []
    for profile in profiles:
        lead = _lead(
            dataset_id=dataset_id,
            resource=f"claim-{profile}",
            index=sequence,
            submitter_user_id=operator.id,
            status=LeadV12Status.DISPATCHED.value,
            now=now,
        )
        assignment = Assignment(
            id=_stable_id(dataset_id, f"claim-assignment-{profile}"),
            lead_id=lead.id,
            company_id=company.id,
            receiver_company_id=company.id,
            supplier_company_id=None,
            status=AssignmentStatus.PENDING_CLAIM.value,
            points_price=DEFAULT_POINTS_PRICE,
            claim_points=DEFAULT_POINTS_PRICE,
            price_version=1,
            lead_snapshot={"synthetic_data": True, "dataset_id": dataset_id},
            assigned_by=operator.id,
            assigned_at=now,
            expires_at=now + timedelta(days=7),
            idempotency_key=f"h04:{dataset_id}:claim-fixture:{profile}",
        )
        lead.current_assignment_id = assignment.id
        db.add(lead)
        claim_assignments.append(assignment)
        claim_cases[str(profile)] = assignment.id
        sequence += 1

    # PostgreSQL enforces the assignment -> lead foreign key during the bulk
    # insert. Keep the dependency order explicit instead of relying on the ORM
    # to infer ordering from scalar foreign-key ids without relationships.
    db.flush()
    db.add_all(claim_assignments)
    db.flush()

    running_balance = initial_points
    assignment_detail_id: str | None = None
    evidence_leads: list[Lead] = []
    evidence_assignments: list[Assignment] = []
    evidence_returns: list[ReturnRequest] = []
    evidence_ledgers: list[PointsLedger] = []
    for profile in profiles:
        return_ids: list[str] = []
        for index in range(profile):
            lead = _lead(
                dataset_id=dataset_id,
                resource=f"evidence-{profile}",
                index=sequence,
                submitter_user_id=operator.id,
                status=LeadV12Status.CLAIMED.value,
                now=now,
            )
            assignment = Assignment(
                id=_stable_id(dataset_id, f"evidence-assignment-{profile}", index),
                lead_id=lead.id,
                company_id=company.id,
                receiver_company_id=company.id,
                supplier_company_id=None,
                status=AssignmentStatus.CLAIMED.value,
                points_price=DEFAULT_POINTS_PRICE,
                claim_points=DEFAULT_POINTS_PRICE,
                price_version=1,
                lead_snapshot={"synthetic_data": True, "dataset_id": dataset_id},
                assigned_by=operator.id,
                assigned_at=now,
                claimed_at=now,
                appeal_deadline_at=now + timedelta(days=30),
                reward_due_at=now + timedelta(days=30),
                first_followup_due_at=now + timedelta(days=30),
                idempotency_key=f"h04:{dataset_id}:evidence-fixture:{profile}:{index}",
            )
            lead.current_assignment_id = assignment.id
            return_request = ReturnRequest(
                id=_stable_id(dataset_id, f"return-{profile}", index),
                assignment_id=assignment.id,
                lead_id=lead.id,
                company_id=company.id,
                reason_code="EMPTY_NUMBER",
                reason_version=1,
                description="H04 synthetic evidence upload fixture",
                status=ReturnV12Status.DRAFT.value,
                submitted_by=receiver.id,
                due_at=now + timedelta(days=30),
                appeal_deadline_at=now + timedelta(days=30),
            )
            running_balance -= DEFAULT_POINTS_PRICE
            ledger = PointsLedger(
                id=_stable_id(dataset_id, f"claim-ledger-{profile}", index),
                account_id=account.id,
                company_id=company.id,
                ledger_type=PointsLedgerType.CLAIM.value,
                delta=-DEFAULT_POINTS_PRICE,
                balance_after=running_balance,
                business_type="V12_ASSIGNMENT_CLAIM",
                business_id=assignment.id,
                idempotency_key=f"v12-claim:{assignment.id}",
                created_by=receiver.id,
                metadata_json={"synthetic_data": True, "dataset_id": dataset_id, "lead_id": lead.id},
                created_at=now + timedelta(microseconds=sequence),
            )
            evidence_leads.append(lead)
            evidence_assignments.append(assignment)
            evidence_returns.append(return_request)
            evidence_ledgers.append(ledger)
            return_ids.append(return_request.id)
            assignment_detail_id = assignment_detail_id or assignment.id
            sequence += 1
        evidence_cases[str(profile)] = return_ids

    db.add_all(evidence_leads)
    db.flush()
    db.add_all(evidence_assignments)
    db.flush()
    db.add_all([*evidence_returns, *evidence_ledgers])
    account.balance = running_balance
    document = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "environment": environment,
        "base_url_origin": origin,
        "synthetic_data": True,
        "assignment_detail_id": assignment_detail_id,
        "dispatch_company_id": company.id,
        "dispatch_cases": dispatch_cases,
        "claim_cases": claim_cases,
        "evidence_cases": evidence_cases,
        "claim_baseline": dict(claim_baseline) if claim_baseline is not None else None,
    }
    validate_dataset(document, profiles=profiles, runtime=True)
    db.flush()
    return document


def _atomic_write(path: Path, content: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)


def write_outputs(
    *,
    dataset: dict[str, Any],
    credentials: DatasetCredentials,
    dataset_path: Path,
    credentials_path: Path,
) -> None:
    _atomic_write(dataset_path, json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", mode=0o644)
    lines = (
        f"V12_PERF_OPERATOR_USERNAME={credentials.operator_username}",
        f"V12_PERF_OPERATOR_PASSWORD={credentials.operator_password}",
        f"V12_PERF_RECEIVER_USERNAME={credentials.receiver_username}",
        f"V12_PERF_RECEIVER_PASSWORD={credentials.receiver_password}",
        f"V12_PERF_OWNER_USERNAME={credentials.owner_username}",
        f"V12_PERF_OWNER_PASSWORD={credentials.owner_password}",
    )
    _atomic_write(credentials_path, "\n".join(lines) + "\n", mode=0o600)


def persist_dataset(
    db: Session,
    *,
    dataset: dict[str, Any],
    credentials: DatasetCredentials,
    dataset_path: Path,
    credentials_path: Path,
) -> None:
    output_paths = (dataset_path, credentials_path)
    if dataset_path == credentials_path or any(path.exists() for path in output_paths):
        raise ValueError("dataset and credentials outputs must be distinct new files")
    try:
        write_outputs(
            dataset=dataset,
            credentials=credentials,
            dataset_path=dataset_path,
            credentials_path=credentials_path,
        )
        db.commit()
    except Exception:
        db.rollback()
        for path in output_paths:
            path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare an isolated synthetic H04 staging capacity dataset")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--expected-database-name", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--environment", choices=("staging", "staging-equivalent"), default="staging-equivalent")
    parser.add_argument("--profiles", default=",".join(str(item) for item in DEFAULT_PROFILES))
    parser.add_argument("--initial-points", type=int, default=DEFAULT_INITIAL_POINTS)
    parser.add_argument("--claim-p95-limit-ms", type=float)
    parser.add_argument("--claim-approval-reference")
    parser.add_argument("--dataset-output", type=Path, default=Path("dist/performance/dataset.json"))
    parser.add_argument("--credentials-output", type=Path, default=Path("/tmp/h04-credentials.env"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url/DATABASE_URL is required")
    try:
        profiles = tuple(int(item.strip()) for item in args.profiles.split(",") if item.strip())
    except ValueError:
        parser.error("--profiles must contain comma-separated integers")
    if (args.claim_p95_limit_ms is None) != (args.claim_approval_reference is None):
        parser.error("--claim-p95-limit-ms and --claim-approval-reference must be supplied together")
    claim_baseline = None
    if args.claim_p95_limit_ms is not None:
        claim_baseline = {
            "approved": True,
            "p95_limit_ms": args.claim_p95_limit_ms,
            "approval_reference": args.claim_approval_reference,
        }

    try:
        validate_credentials_storage(
            platform_name=os.name,
            credentials_path=args.credentials_output,
            running_in_container=(Path("/.dockerenv").exists() or bool(os.environ.get("KUBERNETES_SERVICE_HOST"))),
        )
    except ValueError as exc:
        parser.error(str(exc))

    engine = create_engine(args.database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        parser.error("capacity dataset preparation requires PostgreSQL")
    credentials = credentials_for(args.dataset_id)
    try:
        with Session(engine) as db:
            current_database = str(db.scalar(text("SELECT current_database()")) or "")
            database_environment = str(
                db.scalar(select(func.current_setting(DATABASE_ENVIRONMENT_SETTING, True))) or ""
            )
            settings = get_settings()
            validate_database_target(
                app_env=settings.app_env,
                current_database=current_database,
                expected_database=args.expected_database_name,
                database_environment=database_environment,
            )
            validate_runtime_secrets(
                field_encryption_key=settings.field_encryption_key,
                phone_hash_secret=settings.phone_hash_secret,
                phone_fingerprint_secret=settings.phone_fingerprint_secret,
            )
            dataset = prepare_dataset(
                db,
                dataset_id=args.dataset_id,
                base_url_origin=args.base_url,
                environment=args.environment,
                profiles=profiles,
                credentials=credentials,
                initial_points=args.initial_points,
                claim_baseline=claim_baseline,
            )
            persist_dataset(
                db,
                dataset=dataset,
                credentials=credentials,
                dataset_path=args.dataset_output,
                credentials_path=args.credentials_output,
            )
    finally:
        engine.dispose()
    print(
        f"prepared isolated synthetic dataset {args.dataset_id}: "
        f"dataset={args.dataset_output}, credentials={args.credentials_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
