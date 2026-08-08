from __future__ import annotations

import pytest

from scripts.check_coverage_gate import CRITICAL_FILES, build_report


def _file_summary(*, statements: int = 10, covered_lines: int = 8, branches: int = 4, covered_branches: int = 3):
    return {
        "summary": {
            "num_statements": statements,
            "covered_lines": covered_lines,
            "num_branches": branches,
            "covered_branches": covered_branches,
        }
    }


def test_coverage_report_calculates_line_and_branch_separately() -> None:
    payload = {
        "totals": {
            "num_statements": 100,
            "covered_lines": 80,
            "num_branches": 40,
            "covered_branches": 30,
            "percent_covered": 78.57,
        },
        "files": {path: _file_summary() for path in CRITICAL_FILES},
    }
    report = build_report(payload)
    assert report["global"]["line_percent"] == 80.0
    assert report["global"]["branch_percent"] == 75.0
    assert report["critical_total"]["line_percent"] == 80.0
    assert report["critical_total"]["branch_percent"] == 75.0
    assert report["critical_total"]["target_branch_percent"] == 90.0


def test_coverage_report_fails_if_critical_runtime_file_disappears() -> None:
    files = {path: _file_summary() for path in CRITICAL_FILES}
    files.pop(CRITICAL_FILES[0])
    with pytest.raises(SystemExit, match="missing critical runtime files"):
        build_report({"totals": {}, "files": files})
