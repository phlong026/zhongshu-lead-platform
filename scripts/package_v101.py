#!/usr/bin/env python3
"""Build reviewed V1.0.1 source, Git-history and delivery archives."""
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
DEFAULT_VERSION = "V1.0.1"
ALLOWED_TRACKED_ENV_FILES = {".env.example", ".env.docker.example"}
GENERATED_ARCHIVE_FILES = {"RELEASE_MANIFEST.json", "GIT_HISTORY.txt"}
PROHIBITED_PATTERNS = (
    re.compile(r"(^|/)\.env(?:\..*)?$", re.IGNORECASE),
    re.compile(r"\.(?:db|sqlite|sqlite3)$", re.IGNORECASE),
    re.compile(r"(^|/)storage/", re.IGNORECASE),
    re.compile(r"(^|/)backups/(?!README\.md$)", re.IGNORECASE),
    re.compile(r"(^|/)infra/certs/(?!README\.md$)", re.IGNORECASE),
    re.compile(r"\.(?:pem|key|p12|pfx|crt)$", re.IGNORECASE),
    re.compile(r"(^|/)__pycache__/", re.IGNORECASE),
    re.compile(r"\.pyc$", re.IGNORECASE),
    re.compile(r"(^|/)\.pytest_cache/", re.IGNORECASE),
    re.compile(r"(^|/)\.coverage$", re.IGNORECASE),
)


def git(*args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=text)
    return result.stdout


def repository_is_dirty() -> bool:
    return bool(str(git("status", "--porcelain")).strip())


def tracked_files() -> list[Path]:
    raw = git("ls-files", "-z", text=False)
    assert isinstance(raw, bytes)
    paths = [Path(item.decode("utf-8")) for item in raw.split(b"\0") if item]
    paths = [path for path in paths if path.as_posix() not in GENERATED_ARCHIVE_FILES]
    unsafe = [
        path.as_posix()
        for path in paths
        if path.as_posix() not in ALLOWED_TRACKED_ENV_FILES
        and any(pattern.search(path.as_posix()) for pattern in PROHIBITED_PATTERNS)
    ]
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


def safe_version(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or DEFAULT_VERSION


def zip_info(arcname: str, timestamp: tuple[int, int, int, int, int, int], mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(arcname, date_time=timestamp)
    info.create_system = 3
    info.external_attr = (mode & 0xFFFF) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def git_timestamp() -> tuple[int, int, int, int, int, int]:
    epoch = int(str(git("log", "-1", "--format=%ct")).strip())
    moment = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
    return (max(moment.year, 1980), moment.month, moment.day, moment.hour, moment.minute, moment.second)


def release_manifest(*, version: str, files: list[Path]) -> dict[str, object]:
    return {
        "product": "众墅之家客资审核、派发与积分管理平台",
        "release": version,
        "commit": str(git("rev-parse", "HEAD")).strip(),
        "branch": str(git("rev-parse", "--abbrev-ref", "HEAD")).strip(),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tracked_file_count": len(files),
        "source_archive_policy": "Git tracked files only; secrets and runtime data rejected",
        "included_scope": [
            "WeChat OAuth, secure lead deep links and notification outbox",
            "Feishu resilient incremental lead synchronization and writeback",
            "Franchisee and telesales H5 production experience",
            "Manual dispatch and single points account",
            "Versioned point packages, V1/V2/V3 entitlements, pricing and reconciliation",
            "Role-aware business, region and points reporting",
            "Production validation, TLS proxy, logging, health and backup recovery",
        ],
        "excluded_scope": [
            "Online payment",
            "Automatic, rotation or weighted dispatch",
            "WeChat Mini Program",
            "Cloud outbound calling and automatic native call recording",
        ],
        "production_gates": [
            "Real WeChat official account OAuth and template messages",
            "Real Feishu app and Bitable field mapping",
            "PostgreSQL, private object storage and TLS on target infrastructure",
            "Backup restore drill, mobile-device UAT and gray rollout",
        ],
    }


def build_source_zip(output: Path, *, version: str) -> dict[str, object]:
    files = tracked_files()
    manifest = release_manifest(version=version, files=files)
    timestamp = git_timestamp()
    root_name = f"zhongshu-lead-platform-{version}"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in files:
            source = ROOT / relative
            archive.writestr(
                zip_info(f"{root_name}/{relative.as_posix()}", timestamp, source.stat().st_mode & 0o777),
                source.read_bytes(),
            )
        archive.writestr(
            zip_info(f"{root_name}/RELEASE_MANIFEST.json", timestamp),
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(
            zip_info(f"{root_name}/GIT_HISTORY.txt", timestamp),
            str(git("log", "--oneline", "--decorate", "--all")).encode("utf-8"),
        )
    return manifest


def build_git_bundle(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "bundle", "create", str(output), "--all"], cwd=ROOT, check=True)
    subprocess.run(["git", "bundle", "verify", str(output)], cwd=ROOT, check=True, capture_output=True, text=True)


def copy_if_exists(source: Path, target: Path) -> None:
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def write_delivery_note(path: Path, *, version: str, commit: str, source: Path, bundle: Path) -> None:
    path.write_text(
        "\n".join(
            [
                f"# 众墅之家客资平台 {version} 代码交付说明",
                "",
                f"- Git 提交：`{commit}`",
                "- 交付状态：V1.0.1 生产候选代码；真实第三方与目标基础设施仍需上线 Gate 验证。",
                "- 派发策略：运营人工派发，不包含自动、轮询或权重派发。",
                "- 结算策略：线下付款后人工充值积分，不包含任何线上支付。",
                "",
                "## 文件",
                "",
                f"- `{source.name}`：完整源码，不含密钥、数据库、上传证据、证书私钥和备份。",
                f"- `{bundle.name}`：完整 Git 历史，可使用 `git clone <bundle> <目录>` 恢复。",
                "- `SHA256SUMS.txt`：交付包内文件完整性校验。",
                "- `质量与发布资料/`：测试、评审、发布说明和部署检查资料。",
                "",
                "## 生产前置",
                "",
                "执行生产配置与部署校验，完成微信、飞书、PostgreSQL、私有对象存储、TLS、备份恢复、真机 UAT 和灰度验证后方可正式开放。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def package_release(output_dir: Path, *, version: str, quality_dir: Path | None = None, allow_dirty: bool = False) -> dict[str, Path]:
    if repository_is_dirty() and not allow_dirty:
        raise RuntimeError("repository has uncommitted changes; review and commit before packaging")
    normalized = safe_version(version)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = output_dir / f"众墅之家客资平台_{normalized}_完整源码.zip"
    bundle = output_dir / f"众墅之家客资平台_{normalized}_完整Git提交历史.bundle"
    delivery = output_dir / f"众墅之家客资平台_{normalized}_完整交付包.zip"
    external_checksums = output_dir / f"众墅之家客资平台_{normalized}_SHA256SUMS.txt"

    manifest = build_source_zip(source, version=normalized)
    build_git_bundle(bundle)
    with tempfile.TemporaryDirectory(prefix="zhongshu-v101-") as temp_name:
        temp = Path(temp_name)
        note = temp / "交付说明.md"
        write_delivery_note(note, version=normalized, commit=str(manifest["commit"]), source=source, bundle=bundle)
        quality = temp / "质量与发布资料"
        for relative in (
            "docs/release/RELEASE_NOTES_V1.0.1.md",
            "docs/reviews/INDEX_V1.0.1.md",
            "docs/runbooks/PRODUCTION_CHECKLIST_V1.0.1.md",
            "docs/runbooks/DEPLOYMENT.md",
            "docs/runbooks/BACKUP_RESTORE.md",
        ):
            copy_if_exists(ROOT / relative, quality / Path(relative).name)
        if quality_dir and quality_dir.is_dir():
            for file in sorted(quality_dir.rglob("*")):
                if file.is_file():
                    copy_if_exists(file, quality / "自动检查" / file.relative_to(quality_dir))
        checksums = temp / "SHA256SUMS.txt"
        checksums.write_text(f"{sha256(source)}  {source.name}\n{sha256(bundle)}  {bundle.name}\n", encoding="utf-8")
        with zipfile.ZipFile(delivery, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.write(source, source.name)
            archive.write(bundle, bundle.name)
            archive.write(note, note.name)
            archive.write(checksums, checksums.name)
            for file in sorted(quality.rglob("*")):
                if file.is_file():
                    archive.write(file, f"质量与发布资料/{file.relative_to(quality).as_posix()}")

    external_checksums.write_text(
        f"{sha256(source)}  {source.name}\n"
        f"{sha256(bundle)}  {bundle.name}\n"
        f"{sha256(delivery)}  {delivery.name}\n",
        encoding="utf-8",
    )
    return {"source": source, "bundle": bundle, "delivery": delivery, "checksums": external_checksums}


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the reviewed V1.0.1 release")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/release")
    parser.add_argument("--quality-dir", type=Path, default=None)
    parser.add_argument("--allow-dirty", action="store_true", help="only for isolated packaging tests")
    args = parser.parse_args()
    artifacts = package_release(
        args.output_dir.resolve(),
        version=args.version,
        quality_dir=args.quality_dir.resolve() if args.quality_dir else None,
        allow_dirty=args.allow_dirty,
    )
    print(json.dumps({key: str(value) for key, value in artifacts.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
