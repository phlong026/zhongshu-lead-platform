#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from sqlalchemy import inspect, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.database import SessionLocal
from apps.api.src.core.models import Lead
from apps.api.src.core.state_machine_v12 import map_legacy_lead_status
from apps.api.src.core.v12_enums import LeadV12Status
from apps.api.src.services.reconciliation_v12 import reconcile_v12
from scripts.seed_v101_migration_fixture import FIXTURE_LEAD_ID

_EXPECTED_ACTIVE_STATUSES = (
    "PENDING_CLAIM",
    "CLAIMED",
    "FOLLOWING",
    "RETURN_PENDING",
)
_CAST_RE = re.compile(r"::\s*(?:character\s+varying|text)(?:\s*\[\s*\])?", re.IGNORECASE)


def _unique_constraints(inspector, table: str) -> dict[str, list[str]]:
    return {
        str(item["name"]): list(item.get("column_names") or [])
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    }


def _strip_outer_parentheses(text: str) -> str:
    value = text.strip()
    while len(value) >= 2 and value[0] == "(" and value[-1] == ")":
        depth = 0
        wraps_entire_expression = True
        for index, char in enumerate(value):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    raise RuntimeError("active assignment predicate has unbalanced parentheses")
                if depth == 0 and index != len(value) - 1:
                    wraps_entire_expression = False
                    break
        if depth != 0:
            raise RuntimeError("active assignment predicate has unbalanced parentheses")
        if not wraps_entire_expression:
            break
        value = value[1:-1].strip()
    return value


def _parse_sql_string_list(fragment: str) -> tuple[str, ...]:
    values = tuple(re.findall(r"'([^']*)'", fragment))
    if not values:
        raise RuntimeError("active assignment predicate contains no status literals")
    skeleton = re.sub(r"'[^']*'", "''", fragment)
    if not re.fullmatch(r"\s*''(?:\s*,\s*'')*\s*", skeleton):
        raise RuntimeError("active assignment predicate status list has unexpected SQL structure")
    return values


def _normalize_active_assignment_predicate(predicate: str) -> str:
    """Return one canonical semantic form for the supported PostgreSQL predicates.

    SQLAlchemy creates the migration as ``status IN (...)``. PostgreSQL commonly
    exposes that predicate through the catalog as ``status = ANY (ARRAY[...])``
    with text/varchar casts. We accept only those two equivalent structures and
    require the status set to be exactly the four V1.2 active assignment states.
    Expressions containing NOT/AND/OR, another column, extra literals, or a
    different set therefore fail closed rather than passing on substring checks.
    """

    value = str(predicate or "").strip()
    if not value:
        raise RuntimeError("active assignment partial index predicate is missing")
    value = _CAST_RE.sub("", value)
    value = value.replace('"', "")
    value = re.sub(r"\(\s*status\s*\)", "status", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()
    value = _strip_outer_parentheses(value)

    match = re.fullmatch(r"status\s+IN\s*\((?P<values>.*)\)", value, flags=re.IGNORECASE)
    if match is None:
        match = re.fullmatch(
            r"status\s*=\s*ANY\s*\(\s*\(*\s*ARRAY\s*\[(?P<values>.*)\]\s*\)*\s*\)",
            value,
            flags=re.IGNORECASE,
        )
    if match is None:
        raise RuntimeError(
            "active assignment partial index predicate must be exactly status IN (...) "
            "or PostgreSQL-equivalent status = ANY(ARRAY[...])"
        )

    statuses = _parse_sql_string_list(match.group("values"))
    if len(statuses) != len(_EXPECTED_ACTIVE_STATUSES) or set(statuses) != set(_EXPECTED_ACTIVE_STATUSES):
        raise RuntimeError(
            "active assignment partial index predicate status set mismatch: "
            f"expected={list(_EXPECTED_ACTIVE_STATUSES)}, actual={list(statuses)}"
        )
    return "status IN (" + ",".join(repr(status) for status in _EXPECTED_ACTIVE_STATUSES) + ")"


def _verify_postgres_constraints(bind) -> dict[str, object]:
    if bind.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL migration verification must run against PostgreSQL")
    inspector = inspect(bind)

    assignment_indexes = {
        str(item["name"]): item
        for item in inspector.get_indexes("assignments")
        if item.get("name")
    }
    active_index = assignment_indexes.get("uq_assignments_active_lead_v12")
    if not active_index or not active_index.get("unique"):
        raise RuntimeError("active assignment partial unique index is missing or not unique")
    if list(active_index.get("column_names") or []) != ["lead_id"]:
        raise RuntimeError("active assignment unique index does not target lead_id")
    predicate = str((active_index.get("dialect_options") or {}).get("postgresql_where") or "")
    canonical_predicate = _normalize_active_assignment_predicate(predicate)

    required_unique_constraints = {
        "points_ledgers": {
            "uq_points_idempotency": ["company_id", "idempotency_key"],
        },
        "return_requests": {
            "uq_return_assignment": ["assignment_id"],
        },
        "supplier_lead_rewards": {
            "uq_supplier_reward_assignment": ["assignment_id"],
        },
    }
    observed: dict[str, dict[str, list[str]]] = {}
    for table, required_constraints in required_unique_constraints.items():
        constraints = _unique_constraints(inspector, table)
        observed[table] = constraints
        for name, expected_columns in required_constraints.items():
            actual_columns = constraints.get(name)
            if actual_columns is None:
                raise RuntimeError(f"required unique constraint missing: {table}.{name}")
            if actual_columns != expected_columns:
                raise RuntimeError(
                    f"unique constraint columns mismatch: {table}.{name}; "
                    f"expected={expected_columns}, actual={actual_columns}"
                )

    return {
        "active_assignment_index": {
            "name": "uq_assignments_active_lead_v12",
            "unique": True,
            "columns": ["lead_id"],
            "predicate": predicate,
            "canonical_predicate": canonical_predicate,
        },
        "unique_constraints": observed,
    }


def main() -> int:
    with SessionLocal() as db:
        lead = db.scalar(select(Lead).where(Lead.id == FIXTURE_LEAD_ID))
        if lead is None:
            raise RuntimeError("V1.0.1 migration fixture is missing")
        if not lead.phone_fingerprint:
            raise RuntimeError("historical phone fingerprint was not backfilled")
        if map_legacy_lead_status(lead.status, strict=True) is not LeadV12Status.READY_DISPATCH:
            raise RuntimeError("historical lead status mapping is incorrect")
        constraints = _verify_postgres_constraints(db.get_bind())
        report = reconcile_v12(db)
        fingerprint_length = len(lead.phone_fingerprint)
    payload = {
        "fixture_lead_id": FIXTURE_LEAD_ID,
        "fingerprint_length": fingerprint_length,
        "mapped_status": LeadV12Status.READY_DISPATCH.value,
        "postgres_constraints": constraints,
        "reconciliation": report.to_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
