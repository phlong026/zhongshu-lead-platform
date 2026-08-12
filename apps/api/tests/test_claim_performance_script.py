from __future__ import annotations

import asyncio
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
                                "company_id": "company-1",
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


def test_claim_performance_dataset_requires_company_id(tmp_path) -> None:
    path = tmp_path / "claim.json"
    path.write_text(
        json.dumps(
            {
                "synthetic_data": True,
                "environment": "staging",
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
    with pytest.raises(ValueError, match="requires company_id"):
        load_dataset(path)


def test_distributed_claim_requires_distinct_assignments() -> None:
    cases = [
        {"assignment_id": "same", "company_id": "company-a", "credential_env_prefix": "TENANT_A"},
        {"assignment_id": "same", "company_id": "company-b", "credential_env_prefix": "TENANT_B"},
    ]

    async def run() -> None:
        with pytest.raises(ValueError, match="assignments must be distinct"):
            await run_profile(
                base_url="http://127.0.0.1:18080",
                scenario="distributed",
                profile=2,
                cases=cases,
            )

    asyncio.run(run())


def test_distributed_claim_requires_distinct_receiver_companies() -> None:
    cases = [
        {"assignment_id": "a-1", "company_id": "same-company", "credential_env_prefix": "TENANT_A"},
        {"assignment_id": "a-2", "company_id": "same-company", "credential_env_prefix": "TENANT_B"},
    ]

    async def run() -> None:
        with pytest.raises(ValueError, match="receiver company_ids"):
            await run_profile(
                base_url="http://127.0.0.1:18080",
                scenario="distributed",
                profile=2,
                cases=cases,
            )

    asyncio.run(run())
