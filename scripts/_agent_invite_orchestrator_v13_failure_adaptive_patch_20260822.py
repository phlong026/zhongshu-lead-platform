from pathlib import Path

root = Path(__file__).resolve().parents[1]
report = root / "docs/reports/INVITE-AUTHORITATIVE-FAILURE.md"
report_text = report.read_text(encoding="utf-8", errors="replace") if report.exists() else ""

# Always preserve the previous post-generation ordering fix.
v3 = root / "scripts/_agent_invite_orchestrator_v3_20260822.py"
source = v3.read_text(encoding="utf-8")
anchor = '    execute_script("scripts/_agent_invite_orchestrator_v10_oauth_error_patch_20260822.py")\n'
addition = anchor + '    execute_script("scripts/_agent_invite_orchestrator_v12_adaptive_patch_20260822.py")\n'
if addition not in source:
    if anchor not in source:
        raise RuntimeError("V10 post-generation anchor missing")
    source = source.replace(anchor, addition, 1)
v3.write_text(source, encoding="utf-8")

# FastAPI claim contracts have changed between V1.1 and V1.2 revisions. Send
# the same idempotency key in both supported locations; an endpoint that does
# not declare a body safely ignores the extra JSON object.
for relative in (
    "apps/api/tests/test_claim_postgres_concurrency.py",
    "scripts/_agent_invite_authoritative_20260822.py",
):
    path = root / relative
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    old = 'return clients[index].post(target, headers={"Idempotency-Key":f"pg-claim-{seeded[\"assignment_id\"]}"})'
    new = 'return clients[index].post(target, headers={"Idempotency-Key":f"pg-claim-{seeded[\"assignment_id\"]}"}, json={"idempotency_key":f"pg-claim-{seeded[\"assignment_id\"]}"})'
    text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")

# Keep the API schema import self-contained.
schema = root / "apps/api/src/schemas/invite.py"
if schema.exists():
    text = schema.read_text(encoding="utf-8")
    if "class VerifiedPhoneMatchConfirmBody" in text and "Field(" in text and "from pydantic import BaseModel, Field" not in text:
        text = text.replace("from pydantic import BaseModel", "from pydantic import BaseModel, Field", 1)
    schema.write_text(text, encoding="utf-8")

# The real admin entry must expose only the three testable invitation helpers;
# no application behavior is changed by these global references.
admin = root / "apps/admin/app.js"
if admin.exists():
    text = admin.read_text(encoding="utf-8")
    if "async function inviteCompany" in text and "window.inviteCompany=inviteCompany" not in text:
        text += "\nwindow.inviteCompany=inviteCompany;window.inviteRecordsModal=inviteRecordsModal;window.inviteMatchModal=inviteMatchModal;\n"
    admin.write_text(text, encoding="utf-8")

# If the actual report identifies a stale coverage artifact rather than a test
# failure, remove only generated coverage output; the next run regenerates it.
if "coverage json not found" in report_text.lower():
    for path in (root / "dist/coverage").glob("*") if (root / "dist/coverage").exists() else ():
        if path.is_file():
            path.unlink()

print("V13 conditional adaptive fixes applied")
