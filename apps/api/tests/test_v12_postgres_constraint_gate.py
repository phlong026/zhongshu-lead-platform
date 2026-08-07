from __future__ import annotations

import pytest

import scripts.verify_v12_postgres_migration as verifier


class _Dialect:
    name = "postgresql"


class _Bind:
    dialect = _Dialect()


class _Inspector:
    def __init__(
        self,
        *,
        points_columns: list[str] | None = None,
        predicate: str | None = None,
    ) -> None:
        self.points_columns = points_columns or ["company_id", "idempotency_key"]
        self.predicate = predicate or (
            "status IN ('PENDING_CLAIM','CLAIMED','FOLLOWING','RETURN_PENDING')"
        )

    def get_indexes(self, table: str):
        assert table == "assignments"
        return [
            {
                "name": "uq_assignments_active_lead_v12",
                "unique": True,
                "column_names": ["lead_id"],
                "dialect_options": {"postgresql_where": self.predicate},
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
    assert result["active_assignment_index"]["canonical_predicate"].startswith("status IN")


def test_postgres_constraint_gate_accepts_real_postgres_any_array_form(monkeypatch) -> None:
    actual_postgres_predicate = (
        "((status)::text = ANY ((ARRAY['PENDING_CLAIM'::character varying, "
        "'CLAIMED'::character varying, 'FOLLOWING'::character varying, "
        "'RETURN_PENDING'::character varying])::text[]))"
    )
    monkeypatch.setattr(
        verifier,
        "inspect",
        lambda bind: _Inspector(predicate=actual_postgres_predicate),
    )
    result = verifier._verify_postgres_constraints(_Bind())
    assert result["active_assignment_index"]["canonical_predicate"] == (
        "status IN ('PENDING_CLAIM','CLAIMED','FOLLOWING','RETURN_PENDING')"
    )


def test_postgres_constraint_gate_rejects_inverse_not_in_predicate(monkeypatch) -> None:
    monkeypatch.setattr(
        verifier,
        "inspect",
        lambda bind: _Inspector(
            predicate="status NOT IN ('PENDING_CLAIM','CLAIMED','FOLLOWING','RETURN_PENDING')"
        ),
    )
    with pytest.raises(RuntimeError, match="must be exactly status IN"):
        verifier._verify_postgres_constraints(_Bind())


def test_postgres_constraint_gate_rejects_extra_boolean_predicate(monkeypatch) -> None:
    monkeypatch.setattr(
        verifier,
        "inspect",
        lambda bind: _Inspector(
            predicate=(
                "status IN ('PENDING_CLAIM','CLAIMED','FOLLOWING','RETURN_PENDING') OR TRUE"
            )
        ),
    )
    with pytest.raises(RuntimeError, match="must be exactly status IN"):
        verifier._verify_postgres_constraints(_Bind())


def test_postgres_constraint_gate_rejects_named_constraint_on_wrong_columns(monkeypatch) -> None:
    monkeypatch.setattr(
        verifier,
        "inspect",
        lambda bind: _Inspector(points_columns=["idempotency_key"]),
    )
    with pytest.raises(RuntimeError, match="unique constraint columns mismatch"):
        verifier._verify_postgres_constraints(_Bind())
