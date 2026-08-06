#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.config import get_settings
from apps.api.src.core.security import encrypt_text, hash_phone

FIXTURE_LEAD_ID = "00000000-0000-4000-8000-000000000101"


def main() -> int:
    settings = get_settings()
    if not settings.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("此迁移夹具仅允许在隔离 PostgreSQL 验证库执行")
    now = datetime.now(timezone.utc)
    phone = "13800138000"
    engine = create_engine(settings.database_url, future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO leads (
                    id, source_type, customer_name, phone_encrypted, phone_hash,
                    acquisition_cost_cents, status, imported_at, snapshot_version,
                    raw_payload, created_at, updated_at
                ) VALUES (
                    :id, 'MANUAL', 'V1.0.1 migration fixture', :phone_encrypted, :phone_hash,
                    0, 'QUALIFIED', :now, 1, CAST(:raw_payload AS JSON), :now, :now
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": FIXTURE_LEAD_ID,
                "phone_encrypted": encrypt_text(phone),
                "phone_hash": hash_phone(phone),
                "raw_payload": json.dumps({"fixture": "v1.0.1"}),
                "now": now,
            },
        )
    print(json.dumps({"fixture_lead_id": FIXTURE_LEAD_ID, "created": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
