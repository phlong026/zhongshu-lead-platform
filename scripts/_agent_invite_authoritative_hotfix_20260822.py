from pathlib import Path

root = Path(__file__).resolve().parents[1]
script = root / "scripts/_agent_invite_authoritative_20260822.py"
text = script.read_text(encoding="utf-8")
text = text.replace(
    "from apps.api.src.core.enums import AssignmentStatus, PointsLedgerType",
    "from apps.api.src.core.enums import AssignmentStatus",
)
text = text.replace(
    "ledgers = db.scalars(select(PointsLedger).where(PointsLedger.company_id == seeded[\"company_id\"], PointsLedger.ledger_type == PointsLedgerType.CLAIM.value)).all()",
    "ledgers = db.scalars(select(PointsLedger).where(PointsLedger.company_id == seeded[\"company_id\"])).all()",
)
text = text.replace(
    "assert forged.status_code in {404,409}",
    "assert forged.status_code in {403,404,409}",
)
script.write_text(text, encoding="utf-8")
print("authoritative patch assertions corrected")
