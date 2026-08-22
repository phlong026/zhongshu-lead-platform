from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "dist/agent-logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REPO = os.environ["GITHUB_REPOSITORY"]
BRANCH = "feat/invite-binding-complete"
PR_NUMBER = "82"


def run(
    command: list[str] | str,
    *,
    log_name: str | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    shell: bool = False,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=merged_env,
        shell=shell,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if log_name:
        (LOG_DIR / log_name).write_text(result.stdout or "", encoding="utf-8")
    if result.stdout:
        print(result.stdout[-20000:])
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {command}")
    return result


def restore_from_history(path: str) -> Path:
    target = ROOT / path
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    commits = run(["git", "log", "--all", "--format=%H", "--", path]).stdout.splitlines()
    for commit in commits:
        result = run(["git", "show", f"{commit}:{path}"], check=False)
        if result.returncode == 0:
            target.write_text(result.stdout, encoding="utf-8")
            return target
    raise RuntimeError(f"cannot restore required asset from history: {path}")


def execute_script(path: str) -> None:
    script = restore_from_history(path)
    run([sys.executable, str(script.relative_to(ROOT))], log_name=f"apply-{script.name}.log")


def cleanup_temporary_assets() -> None:
    patterns = (
        "scripts/_agent_invite_*.py",
        ".github/workflows/_agent-invite-*.yml",
        ".github/workflows/_agent-authoritative-invite-*.yml",
        ".github/workflows/pr-source-snapshot.yml",
    )
    for pattern in patterns:
        for path in ROOT.glob(pattern):
            path.unlink(missing_ok=True)


def wait_workflow(head_sha: str, *, label: str, timeout_seconds: int = 3600) -> tuple[int, dict[str, str]]:
    deadline = time.time() + timeout_seconds
    selected: dict | None = None
    while time.time() < deadline:
        response = json.loads(
            run(
                ["gh", "api", f"repos/{REPO}/actions/runs?head_sha={head_sha}&per_page=100"],
                check=True,
            ).stdout
        )
        candidates = [
            item
            for item in response.get("workflow_runs", [])
            if item.get("name") == "Main Release Verification"
        ]
        if candidates:
            selected = sorted(candidates, key=lambda item: item.get("created_at", ""), reverse=True)[0]
            if selected.get("status") == "completed":
                break
        time.sleep(15)
    if not selected or selected.get("status") != "completed":
        raise RuntimeError(f"{label} workflow did not complete before timeout")
    run_id = int(selected["id"])
    (LOG_DIR / f"{label}-run-id.txt").write_text(str(run_id), encoding="utf-8")
    if selected.get("conclusion") != "success":
        run(["gh", "run", "view", str(run_id), "--log-failed"], log_name=f"{label}-failed.log", check=False)
        raise RuntimeError(f"{label} workflow failed: {run_id}")
    jobs_response = json.loads(
        run(["gh", "api", f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"]).stdout
    )
    outcomes = {job["name"]: job.get("conclusion") for job in jobs_response.get("jobs", [])}
    required = {"verify-main", "postgres-migration", "invite-browser-smoke"}
    failed = {name: outcomes.get(name) for name in required if outcomes.get(name) != "success"}
    if failed:
        raise RuntimeError(f"{label} required jobs failed: {failed}")
    return run_id, outcomes


def sanitize(value: str) -> str:
    value = re.sub(r"postgresql\+psycopg://[^@\s]+@", "postgresql+psycopg://[REDACTED]@", value)
    value = re.sub(
        r"(?i)(password|token|secret|authorization)(\s*[=:]\s*)\S+",
        r"\1\2[REDACTED]",
        value,
    )
    return value


def persist_failure(error: BaseException) -> None:
    report = ROOT / "docs/reports/INVITE-AUTHORITATIVE-FAILURE.md"
    parts = [
        "# 邀请绑定 V3 权威门禁失败证据",
        "",
        f"- workflow_run: {os.environ.get('GITHUB_RUN_ID', '')}",
        f"- source_sha: {os.environ.get('GITHUB_SHA', '')}",
        f"- error: {type(error).__name__}: {error}",
        f"- generated_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
    ]
    for log in sorted(LOG_DIR.glob("*.log")):
        content = sanitize(log.read_text(encoding="utf-8", errors="replace"))
        parts.extend(["", f"## {log.name}", "```text", "\n".join(content.splitlines()[-300:]), "```"])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(parts) + "\n", encoding="utf-8")
    run(["git", "config", "user.name", "荣赫智能"], check=False)
    run(["git", "config", "user.email", "peihr66@gmail.com"], check=False)
    run(["git", "add", str(report.relative_to(ROOT))], check=False)
    run(["git", "commit", "-m", "记录邀请绑定 V3 自动门禁失败证据"], check=False)
    run(["git", "push", "origin", f"HEAD:{BRANCH}"], check=False)


def apply_all_patches() -> None:
    h5 = (ROOT / "apps/h5/app.js").read_text(encoding="utf-8")
    admin = (ROOT / "apps/admin/app.js").read_text(encoding="utf-8")
    if "/auth/invites/confirm-start" not in h5 or "renderInviteQr" not in admin:
        execute_script("scripts/_agent_invite_completion_20260822.py")
    service = (ROOT / "apps/api/src/services/invite_binding_service.py").read_text(encoding="utf-8")
    if "PostgreSQL enforces the primary_user_id foreign key" not in service:
        execute_script("scripts/_agent_invite_pg_fk_fix_20260822.py")
    execute_script("scripts/_agent_invite_authoritative_hotfix_20260822.py")
    execute_script("scripts/_agent_invite_authoritative_20260822.py")
    try:
        execute_script("scripts/_agent_invite_retry_fixes_20260822.py")
    except RuntimeError as exc:
        if "cannot restore required asset" not in str(exc):
            raise


def run_quality_gates() -> None:
    run(["node", "--check", "apps/h5/app.js"], log_name="h5-node.log")
    run(["node", "--check", "apps/admin/app.js"], log_name="admin-node.log")
    targeted = [
        "apps/api/tests/test_auth_company.py",
        "apps/api/tests/test_invite_binding_security.py",
        "apps/api/tests/test_invite_preview.py",
        "apps/api/tests/test_wechat_oauth.py",
        "apps/api/tests/test_test_environment_isolation.py",
        "apps/api/tests/test_claim_singleflight.py",
        "apps/api/tests/test_claim_replay_coalescing.py",
        "apps/api/tests/test_invite_frontend_contract.py",
        "apps/api/tests/test_invite_api_contract.py",
    ]
    run([sys.executable, "-m", "pytest", "-q", *targeted], log_name="targeted.log")

    pg_env = {"DATABASE_URL": os.environ["INVITE_POSTGRES_TEST_URL"]}
    run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], log_name="pg-upgrade.log", env=pg_env)
    run(
        [sys.executable, "-m", "pytest", "-q", "apps/api/tests/test_invite_postgres_concurrency.py", "apps/api/tests/test_claim_postgres_concurrency.py"],
        log_name="pg-concurrency.log",
    )
    run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "downgrade", "-1"], log_name="pg-downgrade.log", env=pg_env)
    run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], log_name="pg-reupgrade.log", env=pg_env)

    run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], log_name="playwright-install.log")
    run([sys.executable, "-m", "pytest", "-q", "apps/api/tests/test_invite_browser_smoke.py"], log_name="browser.log")

    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=apps.api.src",
            "--cov-branch",
            "--cov-report=term-missing",
            "--cov-report=json:dist/coverage/coverage.json",
            "--cov-fail-under=74",
        ],
        log_name="full-pytest.log",
    )
    run([sys.executable, "scripts/check_coverage_gate.py", "--coverage", "dist/coverage/coverage.json", "--output", "dist/coverage/critical-coverage.json"], log_name="coverage.log")
    run([sys.executable, "scripts/export_openapi.py", "--output", "dist/openapi/openapi.json"], log_name="openapi.log")
    run([sys.executable, "scripts/check_js.py"], log_name="js.log")
    run([sys.executable, "scripts/secret_scan.py"], log_name="secrets.log")
    run([sys.executable, "-m", "compileall", "-q", "apps", "scripts", "migrations"], log_name="compile.log")
    run([sys.executable, "scripts/performance_v12.py", "--dataset", "performance/v12-staging-dataset.example.json", "--validate-config"], log_name="performance-contract.log")
    run(["git", "diff", "--check"], log_name="diff-check.log")


def commit_verified_result() -> str:
    report = ROOT / "docs/reports/INVITE-BINDING-COMPLETE-DELIVERY.md"
    text = report.read_text(encoding="utf-8") if report.exists() else "# 专属邀请绑定模块交付与门禁报告\n"
    if "## V3 自动化验收" not in text:
        text += """

## V3 自动化验收

- 全量 pytest、分支覆盖率和关键模块覆盖率门禁；
- PostgreSQL 16 邀请创建/绑定并发与领取事务并发；
- Alembic upgrade head、downgrade -1、re-upgrade head；
- Chromium 管理后台与微信 UA 移动 H5 smoke；
- OpenAPI、JavaScript、秘密扫描、Python 编译与性能合同。

真实微信、生产配置、多实例生产等价压测、全角色 UAT 和真实发送供应商仍单列为 `EXTERNAL_PENDING`；本次为 `PRODUCTION_NOT_VERIFIED`。
"""
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(text, encoding="utf-8")

    cleanup_temporary_assets()
    run(["git", "config", "user.name", "荣赫智能"])
    run(["git", "config", "user.email", "peihr66@gmail.com"])
    run(["git", "add", "-A"])
    run(["git", "diff", "--cached", "--check"])
    staged = run(["git", "diff", "--cached", "--quiet"], check=False)
    if staged.returncode != 0:
        message = """完成邀请绑定全链路与 PostgreSQL 验收

完成测试隔离、S01 并发、专属邀请确认、后台复制二维码、H5 微信门禁、邀请管理、手机号和手工匹配、发送适配及审计；补齐真实 PostgreSQL 邀请与领取并发、Chromium、覆盖率、安全和迁移往返。

Constraint: 不提交生产秘密，不以 mock、SQLite 或健康检查冒充生产验证
Confidence: high
Scope-risk: medium
Reversibility: clean
Tested: pytest+coverage、PostgreSQL 16、Chromium、JS、秘密扫描、迁移往返
Not-tested: 真实微信平台、生产配置、真实发送供应商、全角色 UAT"""
        run(["git", "commit", "-m", message])
        run(["git", "push", "origin", f"HEAD:{BRANCH}"], log_name="push.log")
    return run(["git", "rev-parse", "HEAD"]).stdout.strip()


def dispatch_formal(ref: str, head_sha: str, label: str) -> int:
    run(["gh", "workflow", "run", "main-release.yml", "--ref", ref, "-f", "performance_action=none"], log_name=f"{label}-dispatch.log")
    run_id, _ = wait_workflow(head_sha, label=label)
    return run_id


def update_and_merge() -> str:
    body = """## 已完成

- [x] 测试环境隔离
- [x] S01 并发领取与跨进程事务兜底
- [x] P0 专属邀请、主动确认、confirmation intent、OAuth 与主账号保护
- [x] 后台二次确认、复制、固定依赖二维码
- [x] H5 微信确认绑定和完整错误状态
- [x] P1 分页筛选、撤销 404、绑定追溯和审计
- [x] P2 手机号唯一匹配确认、手工匹配、地区检索、发送适配
- [x] PostgreSQL 邀请/领取并发、Chromium、覆盖率、安全、迁移回滚

## 外部门禁

`EXTERNAL_PENDING`：真实微信 WebView、生产配置、生产等价多实例 PostgreSQL、全角色 UAT、真实短信/微信消息供应商。

`PRODUCTION_NOT_VERIFIED`：未以 mock、SQLite、健康检查或普通单元测试冒充生产完成。
"""
    body_path = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "pr82-body.md"
    body_path.write_text(body, encoding="utf-8")
    run(["gh", "pr", "edit", PR_NUMBER, "--body-file", str(body_path)])
    ready = run(["gh", "pr", "view", PR_NUMBER, "--json", "isDraft", "--jq", ".isDraft"]).stdout.strip()
    if ready == "true":
        run(["gh", "pr", "ready", PR_NUMBER])
    duplicate = run(["gh", "pr", "view", "81", "--json", "state", "--jq", ".state"], check=False)
    if duplicate.returncode == 0 and duplicate.stdout.strip() == "OPEN":
        run(["gh", "pr", "close", "81", "--comment", "S01 有效实现已按最新 main 最小重集成到 PR #82，并通过专项及 PostgreSQL 门禁；关闭重复 Draft PR。"])
    run(["gh", "pr", "merge", PR_NUMBER, "--merge", "--delete-branch", "--subject", "完成专属邀请绑定、S01 并发与发布收口"], log_name="merge.log")
    return run(["gh", "pr", "view", PR_NUMBER, "--json", "mergeCommit", "--jq", ".mergeCommit.oid"]).stdout.strip()


def main() -> None:
    try:
        apply_all_patches()
        # Remove transient agent files before secret scanning; deletions are only
        # staged after every gate succeeds, so a failed run leaves the remote branch repairable.
        cleanup_temporary_assets()
        run_quality_gates()
        feature_head = commit_verified_result()
        feature_run = dispatch_formal(BRANCH, feature_head, "formal-feature")
        merge_sha = update_and_merge()
        main_run = dispatch_formal("main", merge_sha, "formal-main")
        comment = (
            f"已合并并完成 main 回归。最终 main SHA：`{merge_sha}`；"
            f"feature CI run：{feature_run}；main CI run：{main_run}。"
            "真实微信、生产配置、生产等价多实例 PostgreSQL、全角色 UAT 和真实外部发送仍为 EXTERNAL_PENDING；PRODUCTION_NOT_VERIFIED。"
        )
        run(["gh", "pr", "comment", PR_NUMBER, "--body", comment], check=False)
        print(json.dumps({"status":"success","feature_head":feature_head,"main_sha":merge_sha,"feature_run":feature_run,"main_run":main_run}, ensure_ascii=False))
    except BaseException as exc:
        persist_failure(exc)
        raise


if __name__ == "__main__":
    main()
