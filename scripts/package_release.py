#!/usr/bin/env python3
"""Create reviewed source, Git-history and complete V1.2 delivery archives.

Only Git-tracked files are included in the source archive. Local databases,
private uploads, caches and environment secrets are therefore excluded by
construction. The delivery archive fails closed when any required V1.2 quality,
review or production runbook is missing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROHIBITED_PATTERNS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"\.(?:db|sqlite|sqlite3)$", re.IGNORECASE),
    re.compile(r"(^|/)storage/"),
    re.compile(r"(^|/)__pycache__/"),
    re.compile(r"\.pyc$"),
    re.compile(r"(^|/)\.pytest_cache/"),
    re.compile(r"(^|/)\.coverage$"),
)
GENERATED_ARCHIVE_FILES = {"RELEASE_MANIFEST.json", "GIT_HISTORY.txt"}
REQUIRED_RELEASE_DOCS = (
    "README.md",
    "RELEASE_MANIFEST.json",
    "docs/quality/TEST_REPORT.md",
    "docs/quality/SECURITY_AUDIT.md",
    "docs/quality/DEPENDENCY_RISK_ACCEPTANCE.md",
    "docs/traceability/IMPLEMENTATION_MATRIX.md",
    "docs/release/RELEASE_NOTES_V1.2.0.md",
    "docs/reviews/INDEX.md",
    "docs/reviews/INDEX_V1.2.md",
    "docs/reviews/51-v1.2-sprint6-auto-review-fixes.md",
    "docs/reviews/53-v1.2-sprint6-comprehensive-final-review.md",
    "docs/runbooks/DEPLOYMENT.md",
    "docs/runbooks/BACKUP_RESTORE.md",
    "docs/runbooks/SECURITY_CHECKLIST.md",
    "docs/runbooks/PRODUCTION_CHECKLIST_V1.2.md",
    "docs/runbooks/V1.2_MIGRATION_RUNBOOK.md",
    "docs/runbooks/V1.2_UAT.md",
    "docs/runbooks/V1.2_GO_NO_GO.md",
    "docs/runbooks/V1.2_ROLLBACK.md",
    "docs/runbooks/V1.2_POST_LAUNCH.md",
    "docs/runbooks/WECHAT_GATE0.md",
)


def git(*args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def repository_is_dirty() -> bool:
    return bool(str(git("status", "--porcelain")).strip())


def tracked_files() -> list[Path]:
    raw = git("ls-files", "-z", text=False)
    assert isinstance(raw, bytes)
    paths = [Path(item.decode("utf-8")) for item in raw.split(b"\0") if item]
    unsafe = [path.as_posix() for path in paths if any(pattern.search(path.as_posix()) for pattern in PROHIBITED_PATTERNS)]
    if unsafe:
        raise RuntimeError(f"tracked private/runtime files detected: {unsafe}")
    missing = [path.as_posix() for path in paths if not (ROOT / path).is_file()]
    if missing:
        raise RuntimeError(f"tracked files missing from worktree: {missing}")
    return sorted(paths, key=lambda item: item.as_posix())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_info(arcname: str, timestamp: tuple[int, int, int, int, int, int], mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(arcname, date_time=timestamp)
    info.create_system = 3
    info.external_attr = (mode & 0xFFFF) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _git_timestamp() -> tuple[int, int, int, int, int, int]:
    epoch = int(str(git("log", "-1", "--format=%ct")).strip())
    moment = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
    year = max(moment.year, 1980)
    return (year, moment.month, moment.day, moment.hour, moment.minute, moment.second)


def validate_release_docs() -> list[Path]:
    files: list[Path] = []
    for relative in REQUIRED_RELEASE_DOCS:
        path = ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"release document missing: {relative}")
        if path.stat().st_size == 0:
            raise RuntimeError(f"release document empty: {relative}")
        files.append(path)
    return files


def build_source_zip(output: Path, *, version: str, dirty: bool) -> dict[str, object]:
    files = tracked_files()
    commit = str(git("rev-parse", "HEAD")).strip()
    branch = str(git("rev-parse", "--abbrev-ref", "HEAD")).strip()
    timestamp = _git_timestamp()
    root_name = f"zhongshu-lead-platform-{version}"
    log_text = str(git("log", "--oneline", "--decorate", "--all"))
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest: dict[str, object] = {
        "product": "众墅之家客资审核、派发与积分管理平台",
        "release": version,
        "commit": commit,
        "branch": branch,
        "dirty_worktree": dirty,
        "generated_at_utc": generated_at,
        "tracked_file_count": len(files),
        "source_archive_policy": "Git tracked files only; runtime data and secrets excluded",
        "quality_gates": [
            "Full pytest, dependency audit and JavaScript checks",
            "Repository secret and Python compile checks",
            "SQLite V1.0.1 to V1.2 migration cycle",
            "PostgreSQL 16 historical migration, semantic reconciliation and constraints",
            "Desktop admin and mobile H5 Chromium smoke",
            "Comprehensive code/security review with no unresolved P0/P1/P2",
        ],
        "runtime_boundaries": [
            "Manual dispatch only; no automatic, random, rotation, weighted or grab-order dispatch",
            "Return evidence requires screenshot OR call recording",
            "Return appeal and supplier reward observation use three workdays",
            "No online payment, WeChat Mini Program, cloud calling or automatic H5 call recording",
            "Real WeChat, target infrastructure, UAT, recovery drill and gray release remain production gates",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in files:
            if relative.as_posix() in GENERATED_ARCHIVE_FILES:
                continue
            source = ROOT / relative
            mode = source.stat().st_mode & 0o777
            info = _zip_info(f"{root_name}/{relative.as_posix()}", timestamp, mode=mode)
            archive.writestr(info, source.read_bytes())
        archive.writestr(
            _zip_info(f"{root_name}/RELEASE_MANIFEST.json", timestamp),
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(
            _zip_info(f"{root_name}/GIT_HISTORY.txt", timestamp),
            log_text.encode("utf-8"),
        )
    return manifest


def build_git_bundle(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "bundle", "create", str(output), "--all"], cwd=ROOT, check=True)
    subprocess.run(["git", "bundle", "verify", str(output)], cwd=ROOT, check=True, capture_output=True, text=True)


def _write_delivery_note(path: Path, *, version: str, commit: str, dirty: bool, files: dict[str, Path]) -> None:
    lines = [
        f"# 众墅之家客资平台 {version} 代码交付说明",
        "",
        f"- Git 提交：`{commit}`",
        f"- 工作区状态：{'包含未提交变更（仅测试构建）' if dirty else '干净'}",
        "- 交付范围：V1.2 可运行代码、迁移与对账工具、自动质量门禁、测试/安全报告、完整评审链与上线 Runbook",
        "",
        "## 文件说明",
        "",
        f"- `{files['source'].name}`：只包含 Git 已跟踪文件；不含数据库、证据、缓存和 `.env`。",
        f"- `{files['bundle'].name}`：完整 Git 提交历史，可使用 `git clone <bundle> <目录>` 恢复仓库。",
        "- `SHA256SUMS.txt`：交付文件完整性校验值。",
        "- `质量与发布资料/`：V1.2 测试、安全审计、依赖风险接受、评审、部署、迁移、UAT、回滚、复盘和发布资料。",
        "",
        "## 本地启动",
        "",
        "```bash",
        "cp .env.example .env",
        "python -m venv .venv",
        ". .venv/bin/activate",
        "pip install -r requirements.txt",
        "python scripts/init_db.py",
        "python scripts/seed_demo.py",
        "uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000",
        "```",
        "",
        "## 生产前置条件",
        "",
        "代码层最终放行要求最新 Codex/人工综合评审无未解决 P0/P1/P2，并且 release-quality、release-postgres-migration、release-browser-smoke 全绿。真实微信公众号、PostgreSQL 全量迁移、私有对象存储、域名 HTTPS、备份恢复、业务 UAT、监控告警、隐私合规和 3–5 家加盟商灰度仍必须在目标环境签字。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _delivery_doc_name(source: Path) -> str:
    """Keep review/runbook files unambiguous when copied into one flat folder."""

    relative = source.relative_to(ROOT).as_posix()
    if relative == "README.md":
        return "README.md"
    if relative == "RELEASE_MANIFEST.json":
        return "RELEASE_MANIFEST.json"
    return relative.replace("/", "__")


def _copy_release_docs(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source in validate_release_docs():
        shutil.copy2(source, target / _delivery_doc_name(source))


def package_release(output_dir: Path, *, version: str, allow_dirty: bool = False) -> dict[str, Path]:
    dirty = repository_is_dirty()
    if dirty and not allow_dirty:
        raise RuntimeError("repository has uncommitted changes; commit and review them before packaging")
    validate_release_docs()
    safe_version = re.sub(r"[^A-Za-z0-9._-]+", "-", version).strip("-") or "release"
    output_dir.mkdir(parents=True, exist_ok=True)
    source = output_dir / f"众墅之家客资平台_{safe_version}_完整源码.zip"
    bundle = output_dir / f"众墅之家客资平台_{safe_version}_完整Git提交历史.bundle"
    delivery = output_dir / f"众墅之家客资平台_{safe_version}_完整交付包.zip"

    manifest = build_source_zip(source, version=safe_version, dirty=dirty)
    build_git_bundle(bundle)

    with tempfile.TemporaryDirectory(prefix="zhongshu-release-") as temp_name:
        temp = Path(temp_name)
        files = {"source": source, "bundle": bundle}
        note = temp / "交付说明.md"
        _write_delivery_note(note, version=safe_version, commit=str(manifest["commit"]), dirty=dirty, files=files)
        quality = temp / "质量与发布资料"
        _copy_release_docs(quality)
        checksums = temp / "SHA256SUMS.txt"
        checksums.write_text(
            f"{sha256(source)}  {source.name}\n{sha256(bundle)}  {bundle.name}\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(delivery, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.write(source, source.name)
            archive.write(bundle, bundle.name)
            archive.write(note, note.name)
            archive.write(checksums, checksums.name)
            for doc in sorted(quality.iterdir()):
                archive.write(doc, f"质量与发布资料/{doc.name}")

    external_checksums = output_dir / f"众墅之家客资平台_{safe_version}_SHA256SUMS.txt"
    external_checksums.write_text(
        f"{sha256(source)}  {source.name}\n"
        f"{sha256(bundle)}  {bundle.name}\n"
        f"{sha256(delivery)}  {delivery.name}\n",
        encoding="utf-8",
    )
    return {
        "source": source,
        "bundle": bundle,
        "delivery": delivery,
        "checksums": external_checksums,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Package reviewed V1.2 source and full Git history")
    parser.add_argument("--version", default="V1.2.0")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "release")
    parser.add_argument("--allow-dirty", action="store_true", help="only for package-script tests")
    args = parser.parse_args()
    artifacts = package_release(args.output_dir.resolve(), version=args.version, allow_dirty=args.allow_dirty)
    print(json.dumps({key: str(value) for key, value in artifacts.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
