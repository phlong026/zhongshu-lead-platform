#!/usr/bin/env python3
"""N2：绑定一致性发布/启动门禁——error 级违规以非零退出码阻断。

供部署流水线与运维手动核查调用；报告打印违规码与细节（不含任何
openid/token 原文，issue 细节只含主键与计数）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.database import SessionLocal, init_database  # noqa: E402
from apps.api.src.services.binding_integrity import audit_primary_binding_integrity  # noqa: E402


def evaluate(db) -> int:
    """跑一次核查并打印报告；存在 error 级违规时返回 1，否则 0。"""

    report = audit_primary_binding_integrity(db)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.valid else 1


def main() -> int:
    init_database()
    with SessionLocal() as db:
        return evaluate(db)


if __name__ == "__main__":
    raise SystemExit(main())
