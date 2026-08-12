from __future__ import annotations

import json

import pytest

from scripts.claim_performance_v12 import load_dataset, metrics, run_profile


def test_claim_performance_metrics_report_tail_latency() -> None:
    result = metrics([10.0, 20.0, 30.0, 40.0, 50.0], failures=0, duration=1.0)
    assert result["p50_ms"] == 30.0
    assert result["p95_ms"] == 48.0
    assert result["p99_ms"] == 49.6
    assert result["throughput_rps"] == 5.0


def test_claim_performance_dataset_requires_synthetic_staging(tmp_path) -> None:
    path = tmp_path / "claim.json"
    path.write_text(
        json.dumps(
            {
                "synthetic_data": True,
                "environment": "staging-equivalent",
                "scenarios": {
                    "replay": {
                        "2": [
                            {
                                "assignment_id": "assignment-1",
                                "credential_env_prefix": "V12_PERF_RECEIVER",
                            }
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    document = load_dataset(path)
    assert document["synthetic_data"] is True

    document["synthetic_data"] = False
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="synthetic_data=true"):
        load_dataset(path)


@pytest.mark.asyncio
async def test_distributed_claim_requires_distinct_assignments() -> None:
    cases = [
        {"assignment_id": "same", "credential_env_prefix": "TENANT_A"},
        {"assignment_id": "same", "credential_env_prefix": "TENANT_B"},
    ]
    with pytest.raises(ValueError, match="assignments must be distinct"):
        await run_profile(
            base_url="http://127.0.0.1:18080",
            scenario="distributed",
            profile=2,
            cases=cases,
        )
