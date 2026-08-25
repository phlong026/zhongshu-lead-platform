from __future__ import annotations

import json
import stat
from datetime import datetime, timedelta, timezone

import pytest

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
    Role,
    User,
    UserRole,
)
from apps.api.src.core.models_v12 import SupplierLeadReward
from scripts.export_five_role_migration_snapshot import build_snapshot, write_snapshot


def test_migration_snapshot_exports_reconciliation_fields_without_credentials_or_lead_pii(
    db, tmp_path
) -> None:
    company = Company(code="SNAPSHOT", name="迁移快照加盟商", status="ACTIVE")
    role = Role(code="FINANCE", name="历史财务", description="待迁移")
    user = User(
        username="snapshot-user",
        password_hash="must-never-export",
        display_name="迁移快照人员",
        email="must-never-export@example.com",
        phone_encrypted="must-never-export",
        phone_hash="must-never-export",
        company=company,
    )
    db.add_all([company, role, user])
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add_all(
        [
            CompanyServiceRegion(company_id=company.id, region_code="310000"),
            CompanyCapability(company_id=company.id, category_code="WHOLE_HOUSE"),
            InviteToken(
                token_hash="must-never-export",
                company_id=company.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                created_by=user.id,
            ),
        ]
    )
    db.flush()
    account = PointsAccount(company_id=company.id, balance=500, version=3)
    lead = Lead(
        source_type="SUPPLIER_H5",
        source_kind="SUPPLIER_H5",
        supplier_company_id=company.id,
        submitter_user_id=user.id,
        customer_name="不得导出",
        phone_encrypted="must-never-export",
        phone_hash="must-never-export",
        need_summary="不得导出",
        raw_payload={"phone": "must-never-export"},
        status="READY_DISPATCH",
        review_status="PASSED",
        region_code="310000",
    )
    db.add_all([account, lead])
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=company.id,
        supplier_company_id=company.id,
        receiver_company_id=company.id,
        status="FOLLOWING",
        points_price=100,
        assigned_by=user.id,
        lead_snapshot={"customer_name": "不得导出"},
        internal_assignee_user_id=user.id,
    )
    db.add(assignment)
    db.flush()
    db.add_all(
        [
            PointsLedger(
                account_id=account.id,
                company_id=company.id,
                ledger_type="RECHARGE",
                delta=500,
                balance_after=500,
                business_type="MANUAL_RECHARGE",
                business_id="receipt-1",
                idempotency_key="must-never-export",
                external_reference="must-never-export",
                metadata_json={"receipt": "must-never-export"},
                created_by=user.id,
            ),
            ReturnRequest(
                assignment_id=assignment.id,
                lead_id=lead.id,
                company_id=company.id,
                reason_code="INVALID_PHONE",
                description="不得导出",
                status="VERIFYING",
                submitted_by=user.id,
            ),
            SupplierLeadReward(
                lead_id=lead.id,
                assignment_id=assignment.id,
                supplier_company_id=company.id,
                receiver_company_id=company.id,
                status="FROZEN",
                claim_points=100,
                reward_points=30,
            ),
        ]
    )
    db.commit()

    snapshot = build_snapshot(db, captured_at=datetime(2026, 8, 26, tzinfo=timezone.utc))

    assert snapshot["schema"] == "five-role-migration-snapshot.v1"
    assert snapshot["captured_at"] == "2026-08-26T00:00:00+00:00"
    assert snapshot["counts"] == {
        "assignments": 1,
        "companies": 1,
        "company_capabilities": 1,
        "company_service_regions": 1,
        "invites": 1,
        "leads": 1,
        "points_accounts": 1,
        "points_ledgers": 1,
        "rewards": 1,
        "returns": 1,
        "users": 1,
    }
    assert snapshot["users"] == [
        {
            "id": user.id,
            "username": "snapshot-user",
            "display_name": "迁移快照人员",
            "status": "ACTIVE",
            "company_id": company.id,
            "session_version": 1,
            "role_codes": ["FINANCE"],
            "last_login_at": None,
        }
    ]
    assert snapshot["leads"] == [
        {
            "id": lead.id,
            "source_type": "SUPPLIER_H5",
            "source_kind": "SUPPLIER_H5",
            "supplier_company_id": company.id,
            "submitter_user_id": user.id,
            "region_code": "310000",
            "category_code": None,
            "brand_code": None,
            "status": "READY_DISPATCH",
            "pending_reason": None,
            "review_status": "PASSED",
            "duplicate_status": None,
            "current_assignment_id": None,
            "imported_at": snapshot["leads"][0]["imported_at"],
            "submitted_at": None,
            "reviewed_at": None,
        }
    ]
    rendered = json.dumps(snapshot, ensure_ascii=False)
    assert "must-never-export" not in rendered
    assert "不得导出" not in rendered

    output = tmp_path / "migration-snapshot.json"
    write_snapshot(snapshot, output)

    assert json.loads(output.read_text(encoding="utf-8")) == snapshot
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_snapshot(snapshot, output)
