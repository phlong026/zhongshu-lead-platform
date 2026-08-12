#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from apps.api.src.core.config import get_settings
from apps.api.src.core.enums import AssignmentStatus, PointsLedgerType
from apps.api.src.core.models import Assignment, Company, Lead, PointsAccount, PointsLedger, User
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from apps.api.src.core.v12_enums import LeadV12Status
from scripts.performance_v12 import DEFAULT_PROFILES, safe_origin
from scripts.prepare_performance_dataset import (
    DATABASE_ENVIRONMENT_SETTING,
    DATASET_ID_PATTERN,
    DEFAULT_POINTS_PRICE,
    DEFAULT_REGION_CODE,
    _atomic_write,
    _lead,
    _password,
    _stable_id,
    _user,
    validate_credentials_storage,
    validate_database_target,
    validate_runtime_secrets,
)


DEFAULT_DISTRIBUTED_COMPANIES = 20
DEFAULT_INITIAL_POINTS = 1_000_000


def credential_prefix(dataset_id: str, company_index: int | None = None, *, hot: bool = False) -> str:
    stem = dataset_id.replace("-", "_").upper()
    if hot:
        return f"P71_{stem}_HOT"
    if company_index is None:
        raise ValueError("company_index is required for distributed credentials")
    return f"P71_{stem}_D{company_index:02d}"


def load_base_h04_dataset(path: Path, profiles: tuple[int, ...]) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or document.get("synthetic_data") is not True:
        raise ValueError("base H04 dataset must declare synthetic_data=true")
    if str(document.get("environment", "")).lower() not in {"staging", "staging-equivalent"}:
        raise ValueError("base H04 dataset must be staging or staging-equivalent")
    company_id = document.get("dispatch_company_id")
    claim_cases = document.get("claim_cases")
    if not isinstance(company_id, str) or not company_id.strip() or not isinstance(claim_cases, dict):
        raise ValueError("base H04 dataset must contain dispatch_company_id and claim_cases")
    for profile in profiles:
        assignment_id = claim_cases.get(str(profile))
        if not isinstance(assignment_id, str) or not assignment_id.strip():
            raise ValueError(f"base H04 dataset is missing claim_cases.{profile}")
    safe_origin(str(document.get("base_url_origin", "")))
    return document


def _validate_inputs(
    dataset_id: str,
    profiles: tuple[int, ...],
    distributed_companies: int,
    initial_points: int,
) -> None:
    if not DATASET_ID_PATTERN.fullmatch(dataset_id):
        raise ValueError("dataset id must be 3-28 lowercase letters, digits, or hyphens")
    if not profiles or len(set(profiles)) != len(profiles):
        raise ValueError("profiles must be unique")
    if any(profile not in DEFAULT_PROFILES for profile in profiles):
        raise ValueError("claim capacity profiles must be 100, 300 and/or 500")
    if not 2 <= distributed_companies <= 50:
        raise ValueError("distributed companies must be between 2 and 50")
    required_hot_points = sum(profiles) * DEFAULT_POINTS_PRICE
    if initial_points < required_hot_points:
        raise ValueError(f"initial points must be at least {required_hot_points}")


def _ensure_unused(db: Session, dataset_id: str) -> None:
    source_token = f"h04:{dataset_id}"
    if db.scalar(select(func.count(Lead.id)).where(Lead.source_app_token == source_token)):
        raise ValueError("claim performance dataset already exists; restore snapshot or choose a new dataset id")
    code_prefix = f"P71-{dataset_id.upper()}-%"
    if db.scalar(select(Company.id).where(Company.code.like(code_prefix))):
        raise ValueError("claim performance company namespace already exists")
    username_prefix = f"p71_{dataset_id.replace('-', '_')}_%"
    if db.scalar(select(User.id).where(User.username.like(username_prefix))):
        raise ValueError("claim performance user namespace already exists")


def _receiver_company(
    db: Session,
    *,
    dataset_id: str,
    resource: str,
    code_suffix: str,
    display_name: str,
    credential_prefix_value: str,
    operator_user_id: str,
    initial_points: int,
    now,
) -> tuple[Company, User, str]:
    password = _password()
    company = Company(
        id=_stable_id(dataset_id, f"company-{resource}"),
        code=f"P71-{dataset_id.upper()}-{code_suffix}",
        name=display_name,
        status="ACTIVE",
        level_code="V1",
        notes=f"Synthetic #71 claim capacity tenant {dataset_id}; restore snapshot after run.",
    )
    db.add(company)
    db.flush()
    username = f"p71_{dataset_id.replace('-', '_')}_{resource}"
    user = _user(
        db,
        dataset_id=dataset_id,
        resource=f"receiver-{resource}",
        username=username,
        password=password,
        role_code="FRANCHISE_OWNER",
        company_id=company.id,
    )
    company.primary_user_id = user.id
    db.add_all(
        [
            CompanyLeadCapability(
                id=_stable_id(dataset_id, f"capability-{resource}"),
                company_id=company.id,
                capability_code="LEAD_RECEIVER",
                active=True,
                review_status="APPROVED",
                reviewed_by=operator_user_id,
                reviewed_at=now,
            ),
            CompanyServiceAreaV12(
                id=_stable_id(dataset_id, f"service-area-{resource}"),
                company_id=company.id,
                region_code=DEFAULT_REGION_CODE,
                region_level="DISTRICT",
                is_primary_city=True,
                active=True,
                review_status="APPROVED",
                reviewed_by=operator_user_id,
                reviewed_at=now,
                review_note="Synthetic #71 claim capacity fixture",
            ),
        ]
    )
    account = PointsAccount(
        id=_stable_id(dataset_id, f"points-account-{resource}"),
        company_id=company.id,
        balance=initial_points,
        version=1,
    )
    db.add(account)
    db.flush()
    db.add(
        PointsLedger(
            id=_stable_id(dataset_id, f"points-seed-{resource}"),
            account_id=account.id,
            company_id=company.id,
            ledger_type=PointsLedgerType.ADJUST.value,
            delta=initial_points,
            balance_after=initial_points,
            business_type="P71_SYNTHETIC_SEED",
            business_id=f"{dataset_id}:{resource}",
            idempotency_key=f"p71:{dataset_id}:{resource}:seed",
            created_by=operator_user_id,
            metadata_json={"synthetic_data": True, "dataset_id": dataset_id, "resource": resource},
            created_at=now,
        )
    )
    credential_lines = (
        f"{credential_prefix_value}_USERNAME={username}\n"
        f"{credential_prefix_value}_PASSWORD={password}\n"
    )
    return company, user, credential_lines


def _claim_fixture(
    *,
    dataset_id: str,
    resource: str,
    index: int,
    receiver: Company,
    receiver_user: User,
    operator_user_id: str,
    supplier_company_id: str,
    now,
) -> tuple[Lead, Assignment]:
    lead = _lead(
        dataset_id=dataset_id,
        resource=resource,
        index=index,
        submitter_user_id=operator_user_id,
        status=LeadV12Status.DISPATCHED.value,
        now=now,
    )
    lead.supplier_company_id = supplier_company_id
    assignment = Assignment(
        id=_stable_id(dataset_id, f"assignment-{resource}", index),
        lead_id=lead.id,
        company_id=receiver.id,
        receiver_company_id=receiver.id,
        supplier_company_id=supplier_company_id,
        status=AssignmentStatus.PENDING_CLAIM.value,
        points_price=DEFAULT_POINTS_PRICE,
        claim_points=DEFAULT_POINTS_PRICE,
        price_version=1,
        lead_snapshot={"synthetic_data": True, "dataset_id": dataset_id, "resource": resource},
        assigned_by=operator_user_id,
        assigned_at=now,
        expires_at=now + __import__("datetime").timedelta(days=7),
        idempotency_key=f"p71:{dataset_id}:{resource}:{index}",
    )
    lead.current_assignment_id = assignment.id
    return lead, assignment


def prepare_claim_dataset(
    db: Session,
    *,
    dataset_id: str,
    base_h04: dict[str, Any],
    profiles: tuple[int, ...],
    distributed_companies: int,
    initial_points: int,
) -> tuple[dict[str, Any], str]:
    from datetime import datetime, timezone

    _validate_inputs(dataset_id, profiles, distributed_companies, initial_points)
    _ensure_unused(db, dataset_id)
    now = datetime.now(timezone.utc)

    operator_password = _password()
    operator = _user(
        db,
        dataset_id=dataset_id,
        resource="p71-operator",
        username=f"p71_{dataset_id.replace('-', '_')}_operator",
        password=operator_password,
        role_code="OPERATION",
    )
    supplier = Company(
        id=_stable_id(dataset_id, "company-supplier"),
        code=f"P71-{dataset_id.upper()}-SUP",
        name=f"P71 synthetic supplier {dataset_id}",
        status="ACTIVE",
        level_code="V1",
        notes="Synthetic supplier used only for #71 claim reward-path load.",
    )
    db.add(supplier)
    db.flush()

    distributed: list[tuple[Company, User, str]] = []
    credential_lines: list[str] = []
    for index in range(distributed_companies):
        prefix = credential_prefix(dataset_id, index + 1)
        company, user, lines = _receiver_company(
            db,
            dataset_id=dataset_id,
            resource=f"d{index + 1:02d}",
            code_suffix=f"D{index + 1:02d}",
            display_name=f"P71 distributed receiver {index + 1:02d}",
            credential_prefix_value=prefix,
            operator_user_id=operator.id,
            initial_points=initial_points,
            now=now,
        )
        distributed.append((company, user, prefix))
        credential_lines.append(lines)

    hot_prefix = credential_prefix(dataset_id, hot=True)
    hot_company, hot_user, hot_lines = _receiver_company(
        db,
        dataset_id=dataset_id,
        resource="hot",
        code_suffix="HOT",
        display_name="P71 hot-account receiver",
        credential_prefix_value=hot_prefix,
        operator_user_id=operator.id,
        initial_points=initial_points,
        now=now,
    )
    credential_lines.append(hot_lines)

    scenarios: dict[str, dict[str, list[dict[str, str]]]] = {
        "replay": {},
        "distributed": {},
        "hot_account": {},
    }
    base_company_id = base_h04["dispatch_company_id"]
    for profile in profiles:
        scenarios["replay"][str(profile)] = [
            {
                "assignment_id": base_h04["claim_cases"][str(profile)],
                "company_id": base_company_id,
                "credential_env_prefix": "V12_PERF_RECEIVER",
            }
        ]

    sequence = 100_000
    leads: list[Lead] = []
    assignments: list[Assignment] = []
    for profile in profiles:
        distributed_cases: list[dict[str, str]] = []
        for offset in range(profile):
            company, user, prefix = distributed[offset % len(distributed)]
            resource = f"distributed-{profile}"
            lead, assignment = _claim_fixture(
                dataset_id=dataset_id,
                resource=resource,
                index=sequence,
                receiver=company,
                receiver_user=user,
                operator_user_id=operator.id,
                supplier_company_id=supplier.id,
                now=now,
            )
            leads.append(lead)
            assignments.append(assignment)
            distributed_cases.append(
                {
                    "assignment_id": assignment.id,
                    "company_id": company.id,
                    "credential_env_prefix": prefix,
                }
            )
            sequence += 1
        scenarios["distributed"][str(profile)] = distributed_cases

        hot_cases: list[dict[str, str]] = []
        for _ in range(profile):
            resource = f"hot-{profile}"
            lead, assignment = _claim_fixture(
                dataset_id=dataset_id,
                resource=resource,
                index=sequence,
                receiver=hot_company,
                receiver_user=hot_user,
                operator_user_id=operator.id,
                supplier_company_id=supplier.id,
                now=now,
            )
            leads.append(lead)
            assignments.append(assignment)
            hot_cases.append(
                {
                    "assignment_id": assignment.id,
                    "company_id": hot_company.id,
                    "credential_env_prefix": hot_prefix,
                }
            )
            sequence += 1
        scenarios["hot_account"][str(profile)] = hot_cases

    db.add_all(leads)
    db.flush()
    db.add_all(assignments)
    db.flush()

    document = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "synthetic_data": True,
        "environment": base_h04["environment"],
        "base_url_origin": safe_origin(base_h04["base_url_origin"]),
        "base_h04_dataset_id": base_h04.get("dataset_id"),
        "distributed_company_count": distributed_companies,
        "scenarios": scenarios,
    }
    return document, "".join(credential_lines)


def persist_outputs(
    db: Session,
    *,
    dataset: dict[str, Any],
    credential_content: str,
    dataset_path: Path,
    credentials_path: Path,
) -> None:
    if dataset_path == credentials_path or dataset_path.exists() or credentials_path.exists():
        raise ValueError("dataset and credentials outputs must be distinct new files")
    try:
        _atomic_write(dataset_path, json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", mode=0o644)
        _atomic_write(credentials_path, credential_content, mode=0o600)
        db.commit()
    except Exception:
        db.rollback()
        dataset_path.unlink(missing_ok=True)
        credentials_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare isolated synthetic #71 distributed/hot Claim fixtures")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--expected-database-name", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--base-h04-dataset", type=Path, required=True)
    parser.add_argument("--profiles", default=",".join(str(item) for item in DEFAULT_PROFILES))
    parser.add_argument("--distributed-companies", type=int, default=DEFAULT_DISTRIBUTED_COMPANIES)
    parser.add_argument("--initial-points", type=int, default=DEFAULT_INITIAL_POINTS)
    parser.add_argument("--dataset-output", type=Path, default=Path("dist/performance/claim-dataset.json"))
    parser.add_argument("--credentials-output", type=Path, default=Path("/tmp/p71-claim-credentials.env"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url/DATABASE_URL is required")
    try:
        profiles = tuple(int(item.strip()) for item in args.profiles.split(",") if item.strip())
        _validate_inputs(args.dataset_id, profiles, args.distributed_companies, args.initial_points)
        base_h04 = load_base_h04_dataset(args.base_h04_dataset, profiles)
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
        parser.error("claim capacity dataset preparation requires PostgreSQL")
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
            dataset, credentials = prepare_claim_dataset(
                db,
                dataset_id=args.dataset_id,
                base_h04=base_h04,
                profiles=profiles,
                distributed_companies=args.distributed_companies,
                initial_points=args.initial_points,
            )
            persist_outputs(
                db,
                dataset=dataset,
                credential_content=credentials,
                dataset_path=args.dataset_output,
                credentials_path=args.credentials_output,
            )
    finally:
        engine.dispose()

    print(
        f"prepared #71 synthetic claim dataset {args.dataset_id}: "
        f"dataset={args.dataset_output}, credentials={args.credentials_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
