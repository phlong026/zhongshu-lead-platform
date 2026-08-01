#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.core.config import Settings
from apps.api.src.core.production import validate_production_settings


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production environment before migration/startup")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    file_values = load_dotenv(args.env_file)
    merged = {**file_values, **dict(os.environ)}
    settings = Settings(_env_file=args.env_file if args.env_file.exists() else None)
    result = validate_production_settings(settings, merged)
    payload = {"valid": result.valid, "errors": list(result.errors), "warnings": list(result.warnings)}
    if not args.quiet or not result.valid:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
