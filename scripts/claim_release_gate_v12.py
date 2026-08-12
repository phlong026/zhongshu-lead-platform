#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.models import Notification, NotificationOutbox
from scripts import claim_performance_v12 as raw_claim_gate


CLAIM_NOTIFICATION_SCENE = "V12_ASSIGNMENT_CLAIMED"
CLAIM_OUTBOX_EVENT_TYPE = "V12_ASSIGNMENT_CLAIMED"
CLAIM_OUTBOX_AGGREGATE_TYPE = "assignment"


async def verify_target_build_identity(
    base_url: str,
    source_commit: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, str]:
    """Fail before load unless the staging API reports the exact candidate revision."""

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=10.0,
        follow_redirects=False,
        transport=transport,
    ) as client:
        response = await client.get("/health/ready")
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("target /health/ready must return a JSON object")
    build_sha = str(body.get("build_sha", "")).strip().lower()
    if build_sha != source_commit:
        raise ValueError(
            f"target API build_sha {build_sha!r} does not match candidate {source_commit!r}"
        )
    if not raw_claim_gate.SOURCE_COMMIT_PATTERN.fullmatch(build_sha):
        raise ValueError("target API build_sha is not a full Git commit SHA")
    return {
        "build_sha": build_sha,
        "version": str(body.get("version", "")),
        "status": str(body.get("status", "")),
    }


def _selected_cases(
    dataset: dict[str, Any],
    *,
    scenarios: list[str],
    profiles: tuple[int, ...],
) -> list[dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    for scenario in scenarios:
        profile_cases = dataset["scenarios"].get(scenario)
        if not isinstance(profile_cases, dict):
            raise ValueError(f"dataset does not contain scenario {scenario}")
        for profile in profiles:
            cases = profile_cases.get(str(profile))
            if not isinstance(cases, list):
                raise ValueError(f"dataset does not contain {scenario}.{profile}")
            for case in cases:
                assignment_id = case["assignment_id"]
                company_id = case["company_id"]
                previous = selected.get(assignment_id)
                if previous is not None and previous["company_id"] != company_id:
                    raise ValueError(f"assignment {assignment_id} is bound to multiple receiver companies")
                selected[assignment_id] = case
    return list(selected.values())


def claim_notification_snapshot(
    database_url: str,
    cases: list[dict[str, str]],
) -> dict[str, Any]:
    """Verify Claim notification and Outbox facts are exact and company-bound."""

    expected_company = {case["assignment_id"]: case["company_id"] for case in cases}
    assignment_ids = list(expected_company)
    expected = len(assignment_ids)
    deep_links = {
        assignment_id: f"/h5/v12-workbench.html?view=assignment&id={assignment_id}"
        for assignment_id in assignment_ids
    }
    event_keys = {
        assignment_id: f"v12:assignment:{assignment_id}:claimed"
        for assignment_id in assignment_ids
    }

    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        raise ValueError("claim notification evidence requires PostgreSQL")
    try:
        with Session(engine) as db:
            notification_rows = db.execute(
                select(
                    Notification.company_id,
                    Notification.scene,
                    Notification.deep_link,
                ).where(
                    Notification.scene == CLAIM_NOTIFICATION_SCENE,
                    Notification.deep_link.in_(list(deep_links.values())),
                )
            ).all()
            outbox_rows = db.execute(
                select(
                    NotificationOutbox.event_key,
                    NotificationOutbox.event_type,
                    NotificationOutbox.aggregate_type,
                    NotificationOutbox.aggregate_id,
                    NotificationOutbox.payload_json,
                ).where(
                    NotificationOutbox.aggregate_id.in_(assignment_ids),
                    NotificationOutbox.event_type == CLAIM_OUTBOX_EVENT_TYPE,
                )
            ).all()
    finally:
        engine.dispose()

    notification_link_counts = Counter(row.deep_link for row in notification_rows)
    outbox_assignment_counts = Counter(row.aggregate_id for row in outbox_rows)

    notification_bound_exact_one = sum(
        1
        for assignment_id, company_id in expected_company.items()
        if sum(
            1
            for row in notification_rows
            if row.company_id == company_id
            and row.scene == CLAIM_NOTIFICATION_SCENE
            and row.deep_link == deep_links[assignment_id]
        )
        == 1
    )
    outbox_bound_exact_one = sum(
        1
        for assignment_id, company_id in expected_company.items()
        if sum(
            1
            for row in outbox_rows
            if row.event_key == event_keys[assignment_id]
            and row.event_type == CLAIM_OUTBOX_EVENT_TYPE
            and row.aggregate_type == CLAIM_OUTBOX_AGGREGATE_TYPE
            and row.aggregate_id == assignment_id
            and isinstance(row.payload_json, dict)
            and row.payload_json.get("business_id") == assignment_id
            and row.payload_json.get("company_id") == company_id
        )
        == 1
    )
    notification_exact_one = sum(
        1 for assignment_id in assignment_ids if notification_link_counts[deep_links[assignment_id]] == 1
    )
    outbox_exact_one = sum(
        1 for assignment_id in assignment_ids if outbox_assignment_counts[assignment_id] == 1
    )

    return {
        "expected_assignments": expected,
        "claim_notifications_total": len(notification_rows),
        "claim_notifications_exact_one": notification_exact_one,
        "claim_notifications_bound_exact_one": notification_bound_exact_one,
        "claim_outbox_total": len(outbox_rows),
        "claim_outbox_exact_one": outbox_exact_one,
        "claim_outbox_bound_exact_one": outbox_bound_exact_one,
        "preflight_valid": len(notification_rows) == 0 and len(outbox_rows) == 0,
        "postclaim_valid": (
            len(notification_rows) == expected
            and notification_exact_one == expected
            and notification_bound_exact_one == expected
            and len(outbox_rows) == expected
            and outbox_exact_one == expected
            and outbox_bound_exact_one == expected
        ),
    }


async def async_main(args) -> dict[str, Any]:
    dataset = raw_claim_gate.load_dataset(Path(args.dataset))
    source_commit = args.source_commit.strip().lower()
    if not raw_claim_gate.SOURCE_COMMIT_PATTERN.fullmatch(source_commit):
        raise ValueError("--source-commit must be the exact 40-character lowercase candidate SHA")
    checked_out_commit = raw_claim_gate.resolve_checked_out_commit()
    if checked_out_commit != source_commit:
        raise ValueError(
            f"--source-commit {source_commit} does not match checked-out HEAD {checked_out_commit}"
        )
    base_url = raw_claim_gate.safe_origin(args.base_url or dataset.get("base_url_origin", ""))
    database_url = args.database_url or raw_claim_gate._required_env("DATABASE_URL")
    profiles = tuple(args.profiles or raw_claim_gate.DEFAULT_PROFILES)
    scenarios = args.scenarios or [
        name
        for name in ("replay", "distributed", "hot_account")
        if name in dataset["scenarios"]
    ]
    cases = _selected_cases(dataset, scenarios=scenarios, profiles=profiles)

    target_identity = await verify_target_build_identity(base_url, source_commit)
    notification_before = await asyncio.to_thread(
        claim_notification_snapshot,
        database_url,
        cases,
    )
    if notification_before["preflight_valid"] is not True:
        raise ValueError(
            f"claim notification facts are not fresh before load: {notification_before}"
        )

    raw_args = SimpleNamespace(
        dataset=args.dataset,
        base_url=base_url,
        database_url=database_url,
        source_commit=source_commit,
        profiles=list(profiles),
        scenarios=list(scenarios),
    )
    raw_report = await raw_claim_gate.async_main(raw_args)
    notification_after = await asyncio.to_thread(
        claim_notification_snapshot,
        database_url,
        cases,
    )
    notifications_valid = notification_after["postclaim_valid"] is True

    return {
        "schema_version": 1,
        "evidence_type": "P71_CLAIM_RELEASE_GATE",
        "source_commit": source_commit,
        "target_identity": target_identity,
        "notification_facts_before": notification_before,
        "notification_facts_after": notification_after,
        "raw_claim_report": raw_report,
        "valid": raw_report.get("valid") is True and notifications_valid,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Issue #71 final candidate-bound Claim release evidence gate"
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--profiles",
        nargs="*",
        type=int,
        choices=raw_claim_gate.DEFAULT_PROFILES,
    )
    parser.add_argument(
        "--scenarios",
        nargs="*",
        choices=sorted(raw_claim_gate.VALID_SCENARIOS),
    )
    parser.add_argument(
        "--output",
        default="dist/performance/p71-claim-release-evidence.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(async_main(args))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
