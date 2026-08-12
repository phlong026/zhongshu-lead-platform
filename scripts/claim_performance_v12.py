#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.performance_v12 import DatabaseSampler, consistency_snapshot, safe_origin


DEFAULT_PROFILES = (100, 300, 500)
VALID_SCENARIOS = {"replay", "distributed", "hot_account"}
SOURCE_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
CLAIM_P95_TARGET_MS = 500.0


class ClaimDatabaseSampler(DatabaseSampler):
    """Use a short sampling interval so sub-second claim lock spikes are visible."""

    async def sample(self) -> None:
        initial = await asyncio.to_thread(self._snapshot)
        self._deadlocks_start = int(initial["deadlocks_total"])
        self.samples.append(initial)
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=0.05)
            except TimeoutError:
                self.samples.append(await asyncio.to_thread(self._snapshot))


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def metrics(latencies: list[float], failures: int, duration: float) -> dict[str, Any]:
    requests = len(latencies)
    successes = requests - failures
    return {
        "requests": requests,
        "successes": successes,
        "failures": failures,
        "error_rate": round(failures / requests, 6) if requests else 1.0,
        "duration_seconds": round(duration, 6),
        "throughput_rps": round(successes / duration, 3) if duration > 0 else 0.0,
        "p50_ms": round(percentile(latencies, 0.50), 3),
        "p95_ms": round(percentile(latencies, 0.95), 3),
        "p99_ms": round(percentile(latencies, 0.99), 3),
        "mean_ms": round(statistics.fmean(latencies), 3) if latencies else 0.0,
    }


def latency_gate(scenario: str, profile: int, p95_ms: float) -> dict[str, Any]:
    hard_gate = scenario in {"replay", "distributed"} and profile in {100, 300}
    if scenario == "hot_account":
        status = "OBSERVE_HOT_ACCOUNT_CAPACITY"
    elif p95_ms <= CLAIM_P95_TARGET_MS:
        status = "PASS"
    elif profile == 500:
        status = "CAPACITY_LIMIT_REACHED"
    else:
        status = "FAIL"
    return {
        "target_p95_ms": CLAIM_P95_TARGET_MS,
        "hard_gate": hard_gate,
        "passed": (not hard_gate) or p95_ms <= CLAIM_P95_TARGET_MS,
        "status": status,
    }


def _required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"required environment variable {name} is not set")
    return value


def _credential_names(prefix: str) -> tuple[str, str]:
    normalized = prefix.strip().upper()
    if not normalized or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in normalized):
        raise ValueError("credential_env_prefix must contain only A-Z, 0-9 and underscore")
    return f"{normalized}_USERNAME", f"{normalized}_PASSWORD"


def load_dataset(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or document.get("synthetic_data") is not True:
        raise ValueError("claim performance dataset must be an object with synthetic_data=true")
    if str(document.get("environment", "")).lower() not in {"staging", "staging-equivalent"}:
        raise ValueError("claim performance dataset requires staging or staging-equivalent")
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, dict):
        raise ValueError("dataset scenarios must be an object")
    for scenario_name, profiles in scenarios.items():
        if scenario_name not in VALID_SCENARIOS or not isinstance(profiles, dict):
            raise ValueError(f"unsupported claim scenario: {scenario_name}")
        for profile, cases in profiles.items():
            if not str(profile).isdigit() or not isinstance(cases, list) or not cases:
                raise ValueError(f"invalid cases for {scenario_name}.{profile}")
            for case in cases:
                if not isinstance(case, dict):
                    raise ValueError("claim cases must be objects")
                assignment_id = case.get("assignment_id")
                company_id = case.get("company_id")
                prefix = case.get("credential_env_prefix")
                if not isinstance(assignment_id, str) or not assignment_id.strip():
                    raise ValueError("each claim case requires assignment_id")
                if not isinstance(company_id, str) or not company_id.strip():
                    raise ValueError("each claim case requires company_id")
                if not isinstance(prefix, str) or not prefix.strip():
                    raise ValueError("each claim case requires credential_env_prefix")
                _credential_names(prefix)
    return document


async def _login(base_url: str, prefix: str) -> httpx.AsyncClient:
    username_env, password_env = _credential_names(prefix)
    client = httpx.AsyncClient(base_url=base_url, timeout=30.0, follow_redirects=False)
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": _required_env(username_env),
            "password": _required_env(password_env),
        },
    )
    response.raise_for_status()
    if not response.cookies.get("access_token"):
        await client.aclose()
        raise RuntimeError(f"login for {prefix} did not return access_token cookie")
    return client


def _validate_profile_cases(scenario: str, profile: int, cases: list[dict[str, str]]) -> list[dict[str, str]]:
    if scenario == "replay":
        if len(cases) != 1:
            raise ValueError("replay scenario must contain exactly one assignment case per profile")
        return [cases[0] for _ in range(profile)]

    if len(cases) < profile:
        raise ValueError(f"{scenario}.{profile} needs at least {profile} distinct assignment cases")
    request_cases = cases[:profile]
    assignment_ids = [case["assignment_id"] for case in request_cases]
    if len(set(assignment_ids)) != len(assignment_ids):
        raise ValueError(f"{scenario}.{profile} assignments must be distinct")

    company_ids = {case["company_id"] for case in request_cases}
    if scenario == "hot_account" and len(company_ids) != 1:
        raise ValueError("hot_account must use one receiver company_id")
    if scenario == "distributed" and len(company_ids) < 2:
        raise ValueError("distributed must use at least two receiver company_ids")
    return request_cases


async def run_profile(
    *,
    base_url: str,
    scenario: str,
    profile: int,
    cases: list[dict[str, str]],
    database_url: str,
) -> dict[str, Any]:
    request_cases = _validate_profile_cases(scenario, profile, cases)
    prefixes = sorted({case["credential_env_prefix"] for case in request_cases})
    company_ids = sorted({case["company_id"] for case in request_cases})
    clients = {prefix: await _login(base_url, prefix) for prefix in prefixes}
    latencies: list[float] = []
    failures = 0
    first_claims = 0
    idempotent_replays = 0
    company_mismatches = 0
    consistency_before = await asyncio.to_thread(consistency_snapshot, database_url)
    sampler = ClaimDatabaseSampler(database_url)
    sampler_task = asyncio.create_task(sampler.sample())
    results: list[tuple[float, bool, bool | None, bool]] = []
    duration = 0.0

    async def request_once(case: dict[str, str]) -> tuple[float, bool, bool | None, bool]:
        client = clients[case["credential_env_prefix"]]
        started = time.perf_counter()
        try:
            response = await client.post(f"/api/v1/v1.2/assignments/{case['assignment_id']}/claim")
            elapsed = (time.perf_counter() - started) * 1000
            if not 200 <= response.status_code < 300:
                return elapsed, False, None, False
            body = response.json().get("data", {})
            if not isinstance(body, dict):
                return elapsed, False, None, False
            assignment = body.get("assignment", {})
            if not isinstance(assignment, dict):
                return elapsed, False, None, False
            raw_idempotent = body.get("idempotent")
            if not isinstance(raw_idempotent, bool):
                return elapsed, False, None, False
            company_matches = assignment.get("company_id") == case["company_id"]
            return elapsed, True, raw_idempotent, company_matches
        except (httpx.HTTPError, ValueError, TypeError):
            return (time.perf_counter() - started) * 1000, False, None, False

    try:
        started = time.perf_counter()
        results = await asyncio.gather(*(request_once(case) for case in request_cases))
        duration = time.perf_counter() - started
    finally:
        for client in clients.values():
            await client.aclose()
        database_metrics = await sampler.finish()
        await sampler_task
    consistency_after = await asyncio.to_thread(consistency_snapshot, database_url)

    for latency, ok, idempotent, company_matches in results:
        latencies.append(latency)
        if not ok:
            failures += 1
            continue
        if not company_matches:
            company_mismatches += 1
        if idempotent is True:
            idempotent_replays += 1
        else:
            first_claims += 1

    expected_first_claims = 1 if scenario == "replay" else profile
    expected_replays = profile - 1 if scenario == "replay" else 0
    result = metrics(latencies, failures, duration)
    latency = latency_gate(scenario, profile, float(result["p95_ms"]))
    scenario_errors: list[str] = []
    if failures:
        scenario_errors.append(f"http_failures={failures}")
    if company_mismatches:
        scenario_errors.append(f"company_mismatches={company_mismatches}")
    if first_claims != expected_first_claims:
        scenario_errors.append(f"first_claims={first_claims}, expected={expected_first_claims}")
    if idempotent_replays != expected_replays:
        scenario_errors.append(f"idempotent_replays={idempotent_replays}, expected={expected_replays}")
    if database_metrics["deadlocks_delta"] != 0:
        scenario_errors.append(f"deadlocks_delta={database_metrics['deadlocks_delta']}")
    for key in (
        "duplicate_claim_ledgers",
        "points_balance_mismatches",
        "duplicate_active_assignments",
    ):
        if int(consistency_after[key]) != 0:
            scenario_errors.append(f"{key}={consistency_after[key]}")
    if latency["hard_gate"] and not latency["passed"]:
        scenario_errors.append(f"p95_ms={result['p95_ms']} exceeds {CLAIM_P95_TARGET_MS}ms target")

    result.update(
        {
            "scenario": scenario,
            "concurrency": profile,
            "credential_count": len(prefixes),
            "receiver_company_count": len(company_ids),
            "first_claims": first_claims,
            "expected_first_claims": expected_first_claims,
            "idempotent_replays": idempotent_replays,
            "expected_idempotent_replays": expected_replays,
            "company_mismatches": company_mismatches,
            "latency_gate": latency,
            "database": database_metrics,
            "consistency_before": consistency_before,
            "consistency_after": consistency_after,
            "scenario_valid": not scenario_errors,
            "scenario_errors": scenario_errors,
        }
    )
    return result


async def async_main(args) -> dict[str, Any]:
    dataset = load_dataset(Path(args.dataset))
    base_url = safe_origin(args.base_url or dataset.get("base_url_origin", ""))
    database_url = args.database_url or _required_env("DATABASE_URL")
    source_commit = args.source_commit.strip().lower()
    if not SOURCE_COMMIT_PATTERN.fullmatch(source_commit):
        raise ValueError("--source-commit must be the exact 40-character lowercase candidate SHA")
    profiles = tuple(args.profiles or DEFAULT_PROFILES)
    scenario_names = args.scenarios or [
        name for name in ("replay", "distributed", "hot_account") if name in dataset["scenarios"]
    ]
    output: dict[str, Any] = {
        "schema_version": 1,
        "synthetic_data": True,
        "environment": dataset["environment"],
        "base_url_origin": base_url,
        "source_commit": source_commit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_p95_target_ms": CLAIM_P95_TARGET_MS,
        "results": [],
    }
    for scenario in scenario_names:
        if scenario not in VALID_SCENARIOS:
            raise ValueError(f"unsupported scenario: {scenario}")
        profile_cases = dataset["scenarios"].get(scenario)
        if not isinstance(profile_cases, dict):
            raise ValueError(f"dataset does not contain scenario {scenario}")
        for profile in profiles:
            cases = profile_cases.get(str(profile))
            if not isinstance(cases, list):
                raise ValueError(f"dataset does not contain {scenario}.{profile}")
            output["results"].append(
                await run_profile(
                    base_url=base_url,
                    scenario=scenario,
                    profile=profile,
                    cases=cases,
                    database_url=database_url,
                )
            )
    output["valid"] = all(item.get("scenario_valid") is True for item in output["results"])
    return output


def parse_args():
    parser = argparse.ArgumentParser(description="Issue #71 claim-only capacity benchmark")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--profiles", nargs="*", type=int, choices=DEFAULT_PROFILES)
    parser.add_argument("--scenarios", nargs="*", choices=sorted(VALID_SCENARIOS))
    parser.add_argument("--output", default="dist/performance/claim-performance-v12.json")
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
