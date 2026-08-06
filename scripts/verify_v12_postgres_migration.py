#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.database import SessionLocal
from apps.api.src.core.models import Lead
from apps.api.src.core.state_machine_v12 import map_legacy_lead_status
from apps.api.src.core.v12_enums import LeadV12Status
from apps.api.src.services.reconciliation_v12 import reconcile_v12
from scripts.seed_v101_migration_fixture import FIXTURE_LEAD_ID


def main() -> int:
    with SessionLocal() as db:
        lead = db.scalar(select(Lead).where(Lead.id == FIXTURE_LEAD_ID))
        if lead is None:
            raise RuntimeError("V1.0.1 migration fixture is missing")
        if not lead.phone_fingerprint:
            raise RuntimeError("historical phone fingerprint was not backfilled")
        if map_legacy_lead_status(lead.status, strict=True) is not LeadV12Status.READY_DISPATCH:
            raise RuntimeError("historical lead status mapping is incorrect")
        report = reconcile_v12(db)
    payload = {
        "fixture_lead_id": FIXTURE_LEAD_ID,
        "fingerprint_length": len(lead.phone_fingerprint),
        "mapped_status": LeadV12Status.READY_DISPATCH.value,
        "reconciliation": report.to_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
