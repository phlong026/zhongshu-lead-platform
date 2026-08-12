from __future__ import annotations

import json

import pytest

from scripts.prepare_claim_performance_dataset import (
    _validate_inputs,
    credential_prefix,
    load_base_h04_dataset,
)


def test_claim_dataset_credential_prefixes_are_stable_and_separated() -> None:
    assert credential_prefix("claim-71", 1) == "P71_CLAIM_71_D01"
    assert credential_prefix("claim-71", 20) == "P71_CLAIM_71_D20"
    assert credential_prefix("claim-71", hot=True) == "P71_CLAIM_71_HOT"
    assert credential_prefix("claim-71", 1) != credential_prefix("claim-71", hot=True)


def test_claim_dataset_requires_supported_profiles_and_enough_points() -> None:
    _validate_inputs("claim-71", (100, 300, 500), 20, 1_000_000)
    with pytest.raises(ValueError, match="100, 300"):
        _validate_inputs("claim-71", (42,), 20, 1_000_000)
    with pytest.raises(ValueError, match="initial points"):
        _validate_inputs("claim-71", (500,), 20, 10_000)


def test_load_base_h04_dataset_requires_all_claim_profiles(tmp_path) -> None:
    path = tmp_path / "h04.json"
    path.write_text(
        json.dumps(
            {
                "synthetic_data": True,
                "environment": "staging-equivalent",
                "base_url_origin": "http://127.0.0.1:18080",
                "dispatch_company_id": "company-h04",
                "claim_cases": {"100": "a100", "300": "a300", "500": "a500"},
            }
        ),
        encoding="utf-8",
    )
    result = load_base_h04_dataset(path, (100, 300, 500))
    assert result["dispatch_company_id"] == "company-h04"

    document = json.loads(path.read_text(encoding="utf-8"))
    del document["claim_cases"]["300"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="claim_cases.300"):
        load_base_h04_dataset(path, (100, 300, 500))
