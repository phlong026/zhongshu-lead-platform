#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECRET_KEYS = {
    "JWT_SECRET",
    "FIELD_ENCRYPTION_KEY",
    "PHONE_HASH_SECRET",
    "PHONE_FINGERPRINT_SECRET",
    "POSTGRES_PASSWORD",
    "WECHAT_APP_SECRET",
    "FEISHU_APP_SECRET",
    "FEISHU_APP_TOKEN",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
}
SECRET_KEY_PATTERN = "|".join(re.escape(key) for key in sorted(SECRET_KEYS))
ENV_ASSIGNMENT_RE = re.compile(
    rf"^[ \t]*(?:export[ \t]+)?({SECRET_KEY_PATTERN})[ \t]*=[ \t]*"
    r"(?:['\"]([^'\"\n]*)['\"]|([^\s#\n]+))",
    re.MULTILINE,
)
QUOTED_MAPPING_RE = re.compile(
    rf"^[ \t]*['\"]({SECRET_KEY_PATTERN})['\"][ \t]*:[ \t]*['\"]([^'\"\n]*)['\"]",
    re.IGNORECASE | re.MULTILINE,
)
YAML_MAPPING_RE = re.compile(
    rf"^[ \t]*({SECRET_KEY_PATTERN})[ \t]*:[ \t]*([^#\n]+)",
    re.MULTILINE,
)
STATIC_SECRET_PATTERNS = (
    ("AWS_ACCESS_KEY_ID", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf", ".xlsx", ".docx", ".zip", ".db"}
PLACEHOLDER_VALUES = {
    "dummy",
    "example",
    "placeholder",
    "todo",
    "unset",
}
PLACEHOLDER_PREFIXES = (
    "change-me",
    "change-this",
    "changeme",
    "ci-",
    "dev-",
    "replace-",
    "replace-with",
    "test-",
    "your-",
)


@dataclass(frozen=True)
class SecretHit:
    path: Path
    key: str
    pattern: str


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    return (
        not normalized
        or (normalized.startswith("<") and normalized.endswith(">"))
        or normalized.startswith("${")
        or normalized in PLACEHOLDER_VALUES
        or normalized.startswith(PLACEHOLDER_PREFIXES)
    )


def _configured_secret_hits(path: Path, text: str) -> list[SecretHit]:
    values: list[tuple[str, str]] = []
    for match in ENV_ASSIGNMENT_RE.finditer(text):
        values.append((match.group(1), match.group(2) or match.group(3) or ""))
    values.extend((match.group(1), match.group(2)) for match in QUOTED_MAPPING_RE.finditer(text))
    values.extend((match.group(1), match.group(2)) for match in YAML_MAPPING_RE.finditer(text))
    return [
        SecretHit(path=path, key=key.upper(), pattern="configured-secret")
        for key, value in values
        if len(value.strip().strip("'\"")) >= 12 and not _looks_like_placeholder(value)
    ]


def find_secret_hits(path: Path, text: str) -> list[SecretHit]:
    hits = _configured_secret_hits(path, text)
    for name, pattern in STATIC_SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(SecretHit(path=path, key=name, pattern=pattern.pattern))
    return hits


def _git_tracked_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def scan_tracked_files(root: Path = ROOT) -> list[SecretHit]:
    hits: list[SecretHit] = []
    for path in _git_tracked_paths(root):
        if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits.extend(find_secret_hits(path.relative_to(root), text))
    return hits


def main() -> int:
    hits = scan_tracked_files()
    if hits:
        for hit in hits:
            print(f"{hit.path}:{hit.key}:{hit.pattern}")
        return 1
    print("no committed secrets detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
