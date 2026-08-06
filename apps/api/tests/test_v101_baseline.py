from __future__ import annotations

from scripts.baseline_v101 import collect_v101_baseline


def test_v101_baseline_is_pii_free_and_uses_only_legacy_tables(db) -> None:
    report = collect_v101_baseline(str(db.get_bind().url))
    assert report["valid"] is True
    assert set(report["metrics"]["table_counts"]) == {
        "leads",
        "assignments",
        "points_accounts",
        "points_ledgers",
        "return_requests",
        "return_evidences",
    }
    serialized = str(report)
    assert "phone_encrypted" not in serialized
    assert "phone_hash" not in serialized
    assert "customer_name" not in serialized
