#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_production_env import load_dotenv

_SENSITIVE_KEY_MARKERS = ("SECRET", "PASSWORD", "TOKEN", "PRIVATE_KEY", "ACCESS_KEY")


def _sensitive_values(env: dict[str, str]) -> tuple[str, ...]:
    values = {
        value
        for key, value in env.items()
        if value and any(marker in key.upper() for marker in _SENSITIVE_KEY_MARKERS)
    }
    return tuple(sorted(values, key=len, reverse=True))


def _redact(text: str, sensitive_values: tuple[str, ...]) -> str:
    redacted = text
    for value in sensitive_values:
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def _run(
    name: str,
    command: list[str],
    *,
    env: dict[str, str],
    sensitive_values: tuple[str, ...],
) -> dict[str, Any]:
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    return {
        "name": name,
        "command": command,
        "returncode": result.returncode,
        "stdout": _redact(result.stdout[-12000:], sensitive_values),
        "stderr": _redact(result.stderr[-12000:], sensitive_values),
        "valid": result.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V1.2 production Go/No-Go preflight")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--require-certificates", action="store_true")
    parser.add_argument("--allow-incomplete-backfill", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "v12-preflight.json")
    args = parser.parse_args()

    values = load_dotenv(args.env_file)
    # Runtime-injected variables have the same precedence used by Settings and
    # validate_production_env.py, so the report reflects the process that will run.
    env = {**values, **os.environ}
    sensitive_values = _sensitive_values(env)
    python = sys.executable
    commands: list[tuple[str, list[str]]] = [
        (
            "production-environment",
            [python, "scripts/validate_production_env.py", "--env-file", str(args.env_file)],
        ),
        (
            "deployment-prerequisites",
            [
                python,
                "scripts/verify_production.py",
                "--env-file",
                str(args.env_file),
                *(["--require-certificates"] if args.require_certificates else []),
            ],
        ),
        ("database-revision", [python, "-m", "alembic", "-c", "alembic.ini", "current", "--check-heads"]),
        (
            "v12-reconciliation",
            [
                python,
                "scripts/reconcile_v12.py",
                *(["--allow-incomplete-backfill"] if args.allow_incomplete_backfill else []),
            ],
        ),
    ]
    checks = [
        _run(name, command, env=env, sensitive_values=sensitive_values)
        for name, command in commands
    ]
    payload = {
        "valid": all(item["valid"] for item in checks),
        "env_file": str(args.env_file),
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
