from __future__ import annotations

import json
from pathlib import Path


def test_release_quality_documents_exist():
    required = [
        "docs/quality/TEST_REPORT.md",
        "docs/traceability/IMPLEMENTATION_MATRIX.md",
        "docs/release/RELEASE_NOTES_V1.0.0-P0.md",
        "docs/release/RELEASE_GATE_REPORT.md",
        "docs/source/PRD_V1.0_执行版.pdf",
        "docs/source/详细开发计划_V1.0.xlsx",
    ]
    for path in required:
        assert Path(path).is_file(), path


def test_openapi_contains_p0_contract_and_no_online_payment():
    document = json.loads(Path("docs/api/openapi.json").read_text(encoding="utf-8"))
    paths = document["paths"]
    required = {
        "/api/v1/leads/feishu/sync",
        "/api/v1/verification/tasks/{task_id}/submit",
        "/api/v1/dispatch/leads/{lead_id}",
        "/api/v1/claims/assignments/{assignment_id}",
        "/api/v1/points/recharge",
        "/api/v1/followups/assignments/{assignment_id}",
        "/api/v1/returns/{return_id}/review",
    }
    assert required <= set(paths)
    assert not any("payment" in path.lower() or "wechat-pay" in path.lower() for path in paths)
