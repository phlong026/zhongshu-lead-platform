#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

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


def derive_compose_database_url(values: dict[str, str]) -> str | None:
    """Mirror docker-compose.yml's DATABASE_URL when only POSTGRES_* is configured."""

    user = values.get("POSTGRES_USER", "").strip()
    password = values.get("POSTGRES_PASSWORD", "").strip()
    database = values.get("POSTGRES_DB", "").strip()
    if not user or not password or not database:
        return None
    return (
        "postgresql+psycopg://"
        f"{quote(user, safe='')}:{quote(password, safe='')}@db:5432/{quote(database, safe='')}"
    )


def settings_for_validation(env_file: Path, merged: dict[str, str]) -> Settings:
    database_url = merged.get("DATABASE_URL", "").strip() or derive_compose_database_url(merged)
    kwargs = {"database_url": database_url} if database_url else {}
    return Settings(_env_file=env_file if env_file.exists() else None, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production environment before migration/startup")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    file_values = load_dotenv(args.env_file)
    merged = {**file_values, **dict(os.environ)}
    if not merged.get("DATABASE_URL"):
        derived = derive_compose_database_url(merged)
        if derived:
            merged["DATABASE_URL"] = derived
    settings = settings_for_validation(args.env_file, merged)
    result = validate_production_settings(settings, merged)
    payload = {"valid": result.valid, "errors": list(result.errors), "warnings": list(result.warnings)}
    if not args.quiet or not result.valid:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
