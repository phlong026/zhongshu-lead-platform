from __future__ import annotations

import pytest

import scripts.verify_v12_postgres_migration as verifier


class _Dialect:
    name = "postgresql"


class _Bind:
    dialect = _Dialect()


class _Inspector:
    def __init__(self, *, points_columns: list[str] | None = None) -> None:
        self.points_columns = points_columns or ["company_id", "idempotency_key"]

    def get_indexes(self, table: str):
        assert table == "assignments"
        return [
            {
                "name": "uq_assignments_active_lead_v12",
                "unique": True,
                "column_names": ["lead_id"],
                "dialect_options": {
                    "postgresql_where": (
                        "status IN ('PENDING_CLAIM','CLAIMED','FOLLOWING','RETURN_PENDING')"
                    )
                },
            }
        ]

    def get_unique_constraints(self, table: str):
        fixtures = {
            "points_ledgers": [
                {"name": "uq_points_idempotency", "column_names": self.points_columns},
            ],
            "return_requests": [
                {"name": "uq_return_assignment", "column_names": ["assignment_id"]},
            ],
            "supplier_lead_rewards": [
                {"name": "uq_supplier_reward_assignment", "column_names": ["assignment_id"]},
            ],
        }
        return fixtures[table]


def test_postgres_constraint_gate_accepts_expected_columns(monkeypatch) -> None:
    monkeypatch.setattr(verifier, "inspect", lambda bind: _Inspector())
    result = verifier._verify_postgres_constraints(_Bind())
    assert result["unique_constraints"]["points_ledgers"]["uq_points_idempotency"] == [
        "company_id",
        "idempotency_key",
    ]


def test_postgres_constraint_gate_rejects_named_constraint_on_wrong_columns(monkeypatch) -> None:
    monkeypatch.setattr(
        verifier,
        "inspect",
        lambda bind: _Inspector(points_columns=["idempotency_key"]),
    )
    with pytest.raises(RuntimeError, match="unique constraint columns mismatch"):
        verifier._verify_postgres_constraints(_Bind())
