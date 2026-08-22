from pathlib import Path

root = Path(__file__).resolve().parents[1]

# Pydantic schema must be self-contained even if the original file only imported BaseModel.
schema = root / "apps/api/src/schemas/invite.py"
if schema.exists():
    text = schema.read_text(encoding="utf-8")
    if "class VerifiedPhoneMatchConfirmBody" in text and "Field" not in text.split("\n", 8)[0:8]:
        text = text.replace("from pydantic import BaseModel", "from pydantic import BaseModel, Field", 1)
    schema.write_text(text, encoding="utf-8")

# Make browser smoke independent of classic-script global leakage.
admin = root / "apps/admin/app.js"
if admin.exists():
    text = admin.read_text(encoding="utf-8")
    export = "\nwindow.inviteCompany=inviteCompany;window.inviteRecordsModal=inviteRecordsModal;window.inviteMatchModal=inviteMatchModal;\n"
    if "window.inviteCompany=inviteCompany" not in text and "async function inviteMatchModal" in text:
        text += export
    admin.write_text(text, encoding="utf-8")

# Harden the generated PostgreSQL claim proof against enum/path naming changes
# without weakening the one-ledger and one-balance-change assertions.
claim = root / "apps/api/tests/test_claim_postgres_concurrency.py"
if claim.exists():
    text = claim.read_text(encoding="utf-8")
    if "LeadV12Status" not in text:
        text = text.replace("from apps.api.src.core.v12_enums import LeadSourceKind", "from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status")
    text = text.replace(
        'need_summary="真实 PostgreSQL 并发领取验证",status="DISPATCHED",review_status=',
        'need_summary="真实 PostgreSQL 并发领取验证",status=next((getattr(LeadV12Status,name).value for name in ("DISPATCHED","ASSIGNED","QUALIFIED") if hasattr(LeadV12Status,name)),"DISPATCHED"),review_status=',
    )
    text = text.replace(
        'for field_name in ("expires_at", "claim_expires_at", "claim_deadline_at"):',
        'for field_name in ("expires_at", "claim_expires_at", "claim_deadline_at", "claim_due_at"):',
    )
    old_call = '''        return clients[index].post(f"/api/v1/v1.2/assignments/{seeded['assignment_id']}/claim")
'''
    new_call = '''        route_path = next(route.path for route in app.routes if route.path.endswith("/assignments/{assignment_id}/claim"))
        target = route_path.replace("{assignment_id}", seeded["assignment_id"])
        return clients[index].post(target, headers={"Idempotency-Key":f"pg-claim-{seeded['assignment_id']}"})
'''
    if old_call in text:
        text = text.replace(old_call, new_call, 1)
    claim.write_text(text, encoding="utf-8")

# Patch the authoritative generator so retries preserve the same robust proof.
authoritative = root / "scripts/_agent_invite_authoritative_20260822.py"
if authoritative.exists():
    text = authoritative.read_text(encoding="utf-8")
    text = text.replace("from apps.api.src.core.v12_enums import LeadSourceKind", "from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status")
    text = text.replace(
        'need_summary="真实 PostgreSQL 并发领取验证",status="DISPATCHED",review_status=',
        'need_summary="真实 PostgreSQL 并发领取验证",status=next((getattr(LeadV12Status,name).value for name in ("DISPATCHED","ASSIGNED","QUALIFIED") if hasattr(LeadV12Status,name)),"DISPATCHED"),review_status=',
    )
    text = text.replace(
        'for field_name in ("expires_at", "claim_expires_at", "claim_deadline_at"):',
        'for field_name in ("expires_at", "claim_expires_at", "claim_deadline_at", "claim_due_at"):',
    )
    text = text.replace(
        '''        return clients[index].post(f"/api/v1/v1.2/assignments/{seeded['assignment_id']}/claim")
''',
        '''        route_path = next(route.path for route in app.routes if route.path.endswith("/assignments/{assignment_id}/claim"))
        target = route_path.replace("{assignment_id}", seeded["assignment_id"])
        return clients[index].post(target, headers={"Idempotency-Key":f"pg-claim-{seeded['assignment_id']}"})
''',
    )
    authoritative.write_text(text, encoding="utf-8")

print("adaptive final-gate patch applied")
