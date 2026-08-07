from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(
    not (ROOT / ".git").exists(),
    reason="clean-worktree contract requires a Git checkout",
)


def test_test_suite_does_not_modify_tracked_repository_files() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    dirty = result.stdout.strip()
    assert not dirty, f"test suite modified tracked repository files:\n{dirty}"
