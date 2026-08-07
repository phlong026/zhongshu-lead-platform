#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.src.main import app


def openapi_text() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def export_openapi(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(openapi_text(), encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the live V1.2 OpenAPI contract")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "openapi" / "openapi.json",
        help="generated artifact path; defaults under ignored dist/ so the Git worktree stays clean",
    )
    args = parser.parse_args()
    target = export_openapi(args.output.resolve())
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
