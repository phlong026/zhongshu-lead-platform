from __future__ import annotations

import argparse
import json
from pathlib import Path


CRITICAL_FILES = (
    "apps/api/src/core/auth.py",
    "apps/api/src/services/auth_service.py",
    "apps/api/src/services/rbac.py",
    "apps/api/src/services/points_service.py",
    "apps/api/src/services/return_v12.py",
    "apps/api/src/services/supplier_reward_v12.py",
    "apps/api/src/routers/v12_dispatch.py",
)


def _percentage(covered: int, total: int) -> float:
    return 100.0 if total <= 0 else (covered / total) * 100.0


def _summary(raw: dict) -> dict[str, float | int]:
    statements = int(raw.get("num_statements", 0))
    covered_lines = int(raw.get("covered_lines", 0))
    branches = int(raw.get("num_branches", 0))
    covered_branches = int(raw.get("covered_branches", 0))
    return {
        "statements": statements,
        "covered_lines": covered_lines,
        "line_percent": round(_percentage(covered_lines, statements), 2),
        "branches": branches,
        "covered_branches": covered_branches,
        "branch_percent": round(_percentage(covered_branches, branches), 2),
    }


def build_report(payload: dict) -> dict:
    files = payload.get("files", {})
    missing = [path for path in CRITICAL_FILES if path not in files]
    if missing:
        raise SystemExit(
            "coverage report missing critical runtime files: " + ", ".join(missing)
        )

    critical: dict[str, dict] = {}
    statement_total = covered_line_total = branch_total = covered_branch_total = 0
    for path in CRITICAL_FILES:
        item = _summary(files[path].get("summary", {}))
        critical[path] = item
        statement_total += int(item["statements"])
        covered_line_total += int(item["covered_lines"])
        branch_total += int(item["branches"])
        covered_branch_total += int(item["covered_branches"])

    critical_total = {
        "statements": statement_total,
        "covered_lines": covered_line_total,
        "line_percent": round(_percentage(covered_line_total, statement_total), 2),
        "branches": branch_total,
        "covered_branches": covered_branch_total,
        "branch_percent": round(_percentage(covered_branch_total, branch_total), 2),
        "target_line_percent": 90.0,
        "target_branch_percent": 90.0,
    }
    return {
        "global": _summary(payload.get("totals", {})),
        "critical_total": critical_total,
        "critical_files": critical,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", default="dist/coverage/coverage.json")
    parser.add_argument("--output", default="dist/coverage/critical-coverage.json")
    parser.add_argument("--min-global-line", type=float, default=75.0)
    parser.add_argument("--min-global-branch", type=float, default=75.0)
    args = parser.parse_args()

    coverage_path = Path(args.coverage)
    if not coverage_path.is_file():
        raise SystemExit(f"coverage json not found: {coverage_path}")
    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    report = build_report(payload)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    global_summary = report["global"]
    critical_summary = report["critical_total"]
    print(
        "coverage global: "
        f"line={global_summary['line_percent']:.2f}% "
        f"branch={global_summary['branch_percent']:.2f}%"
    )
    print(
        "coverage critical: "
        f"line={critical_summary['line_percent']:.2f}% "
        f"branch={critical_summary['branch_percent']:.2f}% "
        "target=90.00%"
    )
    for path, item in report["critical_files"].items():
        print(
            f"  {path}: line={item['line_percent']:.2f}% "
            f"branch={item['branch_percent']:.2f}%"
        )

    failures: list[str] = []
    if float(global_summary["line_percent"]) < args.min_global_line:
        failures.append(
            f"global line coverage {global_summary['line_percent']:.2f}% < {args.min_global_line:.2f}%"
        )
    if float(global_summary["branch_percent"]) < args.min_global_branch:
        failures.append(
            f"global branch coverage {global_summary['branch_percent']:.2f}% < {args.min_global_branch:.2f}%"
        )
    if failures:
        raise SystemExit("coverage gate failed: " + "; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
