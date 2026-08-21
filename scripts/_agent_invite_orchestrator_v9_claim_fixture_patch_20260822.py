from pathlib import Path

root = Path(__file__).resolve().parents[1]


def patch_text(text: str) -> str:
    text = text.replace(
        "from apps.api.src.services.auth_service import create_internal_user\nfrom apps.api.src.services.rbac import seed_rbac",
        "from apps.api.src.schemas.company import CompanyCreateBody\nfrom apps.api.src.services.auth_service import create_internal_user\nfrom apps.api.src.services.company_service import create_company\nfrom apps.api.src.services.rbac import seed_rbac",
    )
    old = '''        company = Company(code=f"PG-CLAIM-{suffix}", name=f"PostgreSQL 领取并发 {suffix}", status="ACTIVE", level_code="V1")
        db.add(company); db.flush()
        owner = create_internal_user(db, username=f"pg_claim_owner_{suffix}", password="PgClaimOwner123!", display_name="PostgreSQL 领取用户", role_code="FRANCHISE_OWNER", company_id=company.id)
        operator = create_internal_user(db, username=f"pg_claim_operator_{suffix}", password="PgClaimOperator123!", display_name="PostgreSQL 派发用户", role_code="OPERATION")
        company.primary_user_id = owner.id
        account = PointsAccount(company_id=company.id, balance=1000, version=1)
        db.add(account)
'''
    new = '''        company = create_company(db, CompanyCreateBody(code=f"PG-CLAIM-{suffix}",name=f"PostgreSQL 领取并发 {suffix}",owner_name="并发负责人",region_codes=["310115"],capabilities=[{"category_code":"OLD_RENOVATION","brand_code":"ZHONGSHU"}]))
        owner = create_internal_user(db, username=f"pg_claim_owner_{suffix}", password="PgClaimOwner123!", display_name="PostgreSQL 领取用户", role_code="FRANCHISE_OWNER", company_id=company.id)
        operator = create_internal_user(db, username=f"pg_claim_operator_{suffix}", password="PgClaimOperator123!", display_name="PostgreSQL 派发用户", role_code="OPERATION")
        company.primary_user_id = owner.id
        account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company.id))
        assert account is not None
        account.balance = 1000
        account.version = max(int(account.version or 0), 1)
'''
    if old in text:
        text = text.replace(old, new, 1)
    text = text.replace(
        '''        if hasattr(Assignment, "expires_at"):
            assignment_values["expires_at"] = now + timedelta(hours=24)
        elif hasattr(Assignment, "claim_expires_at"):
            assignment_values["claim_expires_at"] = now + timedelta(hours=24)
''',
        '''        deadline = now + timedelta(hours=24)
        for field_name in ("expires_at", "claim_expires_at", "claim_deadline_at"):
            if hasattr(Assignment, field_name):
                assignment_values[field_name] = deadline
                break
''',
    )
    return text

for relative in (
    "scripts/_agent_invite_authoritative_20260822.py",
    "scripts/_agent_invite_retry_fixes_20260822.py",
    "apps/api/tests/test_claim_postgres_concurrency.py",
):
    path = root / relative
    if path.exists():
        path.write_text(patch_text(path.read_text(encoding="utf-8")), encoding="utf-8")

print("PostgreSQL claim fixture aligned with business company creation")
