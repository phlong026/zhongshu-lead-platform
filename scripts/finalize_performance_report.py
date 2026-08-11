from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.performance_v12 import DEFAULT_PROFILES, load_target_metrics


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def finalize_report(
    preview_report: dict[str, Any],
    *,
    preview_report_sha256: str,
    target_metrics_path: Path,
    signoff: dict[str, Any],
    github_run_id: str,
    expected_source_commit: str,
) -> dict[str, Any]:
    if not github_run_id.isdigit() or int(github_run_id) <= 0:
        raise ValueError("github_run_id must be a positive integer")
    if preview_report.get("signoff", {}).get("status") != "PENDING":
        raise ValueError("preview report must retain PENDING signoff")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_source_commit):
        raise ValueError("expected_source_commit must be a lowercase 40-character Git commit SHA")
    if preview_report.get("source_commit_sha") != expected_source_commit:
        raise ValueError("preview report source commit does not match the trusted finalize commit")
    profiles = preview_report.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != {str(value) for value in DEFAULT_PROFILES}:
        raise ValueError("preview report must contain the exact 100/300/500 profiles")
    if not all(isinstance(profile, dict) for profile in profiles.values()):
        raise ValueError("preview report profiles must be objects")
    if any(profile.get("target_infrastructure") is not None for profile in profiles.values()):
        raise ValueError("preview report must not contain pre-attached target infrastructure evidence")
    if signoff.get("status") != "APPROVED":
        raise ValueError("final signoff must have status=APPROVED")

    finalized = copy.deepcopy(preview_report)
    for profile in DEFAULT_PROFILES:
        finalized["profiles"][str(profile)]["target_infrastructure"] = load_target_metrics(
            target_metrics_path, profile
        )
    artifact_name = f"staging-performance-{github_run_id}"
    finalized["preview_evidence"] = {
        "github_run_id": github_run_id,
        "artifact_name": artifact_name,
        "report_sha256": preview_report_sha256,
        "source_commit_sha": expected_source_commit,
    }
    finalized["signoff"] = copy.deepcopy(signoff)
    return finalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind signed H04 evidence to an immutable preview artifact")
    parser.add_argument("--preview-report", type=Path, required=True)
    parser.add_argument("--target-metrics", type=Path, required=True)
    parser.add_argument("--signoff", type=Path, required=True)
    parser.add_argument("--github-run-id", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    preview_bytes = args.preview_report.read_bytes()
    preview_report = json.loads(preview_bytes.decode("utf-8-sig"))
    signoff = json.loads(args.signoff.read_text(encoding="utf-8-sig"))
    if not isinstance(preview_report, dict) or not isinstance(signoff, dict):
        raise ValueError("preview report and signoff roots must be objects")
    finalized = finalize_report(
        preview_report,
        preview_report_sha256=_sha256_bytes(preview_bytes),
        target_metrics_path=args.target_metrics,
        signoff=signoff,
        github_run_id=args.github_run_id,
        expected_source_commit=args.expected_source_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(finalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"signed performance report bound to preview artifact: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
