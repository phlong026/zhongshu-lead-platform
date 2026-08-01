#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json

from apps.api.src.core.database import SessionLocal, init_database
from apps.api.src.services.bootstrap import seed_demo


if __name__ == "__main__":
    init_database()
    with SessionLocal() as db:
        result = seed_demo(db)
        db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
