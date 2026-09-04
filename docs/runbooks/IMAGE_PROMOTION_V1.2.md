# V1.2 绿色扫描镜像晋级与发布 SOP

## 1. 强制原则

生产发布不得重新构建已经通过 Security Analysis 的应用镜像。

唯一允许晋级的构建产物是：

- `main` 分支目标 commit 的 **post-merge Security Analysis** 成功 run；
- 该 run 生成的 `security-candidate-image-<run_id>` artifact；
- artifact 内的 `app-image.tar` 与 `scan-subject.json`。

PR 与手工触发的 Security Analysis 只保留评审 evidence，不生成 `security-candidate-image-*`。生产来源必须是合并后 `main` 相同提交由 push 事件真实通过 Security Analysis 后生成的 artifact。

如果 artifact 已过期，只允许使用 `gh run rerun <原始 main push run_id>` 重跑同一条 push run。若原始 run 已无法重跑，则维持 `NO-GO`，不得用手工 workflow、发布机重建或另一个 commit 的产物代替。

## 2. 为什么禁止重建

Docker build 可能受以下输入影响：

- package registry 当前状态；
- 传递依赖；
- 基础镜像内容；
- 构建器版本与网络返回；
- 上游资源变化。

即使 Dockerfile、requirements 和 Git commit 不变，重新 build 也不等价于“发布之前扫描过的那一组镜像字节”。H07 因此要求安全扫描通过后保存 exact image archive，再晋级该 archive。

## 3. 下载证据

必须从受信任的 `main` checkout 查询 GitHub API，先绑定真实 run、正式 workflow 和 artifact ID，再下载。artifact 内自报的 provenance 只能作为第二层核对，不能替代 GitHub 服务端元数据。

```bash
set -euo pipefail

export GITHUB_REPOSITORY='phlong026/zhongshu-lead-platform'
export SECURITY_RUN_ID='<main push Security Analysis run id>'
export REPO_ROOT="$(git rev-parse --show-toplevel)"

cd "$REPO_ROOT"
git fetch origin main
test "$(git branch --show-current)" = 'main'
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=all -- scripts/check_security_promotion_source.py)"
test "$(git hash-object "$REPO_ROOT/scripts/check_security_promotion_source.py")" = \
  "$(git rev-parse HEAD:scripts/check_security_promotion_source.py)"
export EXPECTED_MAIN_SHA="$(git rev-parse HEAD)"
mkdir -p "$REPO_ROOT/dist/security-promotion"
export PROMOTION_DIR="$(mktemp -d "$REPO_ROOT/dist/security-promotion/${SECURITY_RUN_ID}.XXXXXX")"
gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SECURITY_RUN_ID" \
  > "$PROMOTION_DIR/github-run.json"
gh api "repos/$GITHUB_REPOSITORY/actions/workflows/security-analysis.yml" \
  > "$PROMOTION_DIR/github-workflow.json"
gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SECURITY_RUN_ID/artifacts?per_page=100" \
  > "$PROMOTION_DIR/github-artifacts.json"

python3 -I "$REPO_ROOT/scripts/check_security_promotion_source.py" \
  --run "$PROMOTION_DIR/github-run.json" \
  --workflow "$PROMOTION_DIR/github-workflow.json" \
  --artifacts "$PROMOTION_DIR/github-artifacts.json" \
  --expected-repository "$GITHUB_REPOSITORY" \
  --expected-sha "$EXPECTED_MAIN_SHA" \
  --output "$PROMOTION_DIR/security-promotion-source.json"

export CANDIDATE_ARTIFACT_ID="$(python3 -I -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["candidate_artifact_id"])' \
  "$PROMOTION_DIR/security-promotion-source.json")"
export EVIDENCE_ARTIFACT_ID="$(python3 -I -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["evidence_artifact_id"])' \
  "$PROMOTION_DIR/security-promotion-source.json")"

mkdir -p "$PROMOTION_DIR/candidate" "$PROMOTION_DIR/evidence"
gh api "repos/$GITHUB_REPOSITORY/actions/artifacts/$CANDIDATE_ARTIFACT_ID/zip" \
  > "$PROMOTION_DIR/candidate.zip"
gh api "repos/$GITHUB_REPOSITORY/actions/artifacts/$EVIDENCE_ARTIFACT_ID/zip" \
  > "$PROMOTION_DIR/evidence.zip"
unzip -q "$PROMOTION_DIR/candidate.zip" -d "$PROMOTION_DIR/candidate"
unzip -q "$PROMOTION_DIR/evidence.zip" -d "$PROMOTION_DIR/evidence"
cd "$PROMOTION_DIR"
```

该命令块使用 `set -euo pipefail`；任一 checkout、API 或 validator 检查失败都会在下载前终止。`check_security_promotion_source.py` 必须确认 GitHub API 返回的 `event=push`、`head_branch=main`、`head_sha=EXPECTED_MAIN_SHA`、成功结论、正式 workflow ID/path，并把两个未过期 artifact ID 绑定到同一 run；下载也只使用这两个已验证 ID。不得使用他人提供或手工编辑的 API JSON。

随后只从该 run 下载：

1. `security-candidate-image-<run_id>`：
   - `app-image.tar`
   - `scan-subject.json`
2. `security-analysis-<run_id>`：
   - `security-gate.json`
   - `trivy-image.json`
   - `sbom.cdx.json`
   - Semgrep/Trivy scanner identity 与日志证据。

候选镜像 artifact 默认只保留 7 天；安全证据 artifact 保留 30 天。

## 4. 晋级前核验

先确认 `security-gate.json`：

- `valid == true`；
- `blocking_count == 0`；
- `provenance.event_name == "push"`；
- `provenance.git_ref == "refs/heads/main"`；
- `provenance.candidate_sha == provenance.policy_sha ==` 待发布的 main commit SHA；
- `provenance.waiver_registry_sha256` 等于同一 evidence artifact 中 `waivers-policy.json` 的 SHA-256；
- `scan_subject.schema_version == 2`，且 `image_ref` / `image_id` / `runtime_image_id` / `manifest_digest` / `archive_sha256` 存在；
- 所有 active waiver 仍在有效期内。

```bash
python - <<'PY'
import hashlib
import json
from pathlib import Path

gate = json.loads(Path('evidence/security-gate.json').read_text(encoding='utf-8'))
source = json.loads(Path('security-promotion-source.json').read_text(encoding='utf-8'))
provenance = gate['provenance']
assert provenance['event_name'] == 'push'
assert provenance['git_ref'] == 'refs/heads/main'
assert provenance['candidate_sha'] == provenance['policy_sha'] == source['main_commit_sha']
waiver_sha = hashlib.sha256(Path('evidence/waivers-policy.json').read_bytes()).hexdigest()
assert waiver_sha == provenance['waiver_registry_sha256']
print('trusted main security evidence:', provenance['candidate_sha'])
PY
```

再核对 candidate artifact：

```bash
python - <<'PY'
import hashlib
import json
from pathlib import Path

subject = json.loads(Path('candidate/scan-subject.json').read_text(encoding='utf-8'))
actual = hashlib.sha256(Path('candidate/app-image.tar').read_bytes()).hexdigest()
expected = subject['archive_sha256']
assert actual == expected, (actual, expected)
print('archive sha256 verified:', actual)
print('expected image id:', subject['image_id'])
print('verified runtime identities:', subject['runtime_image_id'], subject['manifest_digest'])
print('scanned image ref:', subject['image_ref'])
PY
```

SHA-256 不一致直接 `NO-GO`。

## 5. 加载 exact scanned image

```bash
docker load -i candidate/app-image.tar
```

然后读取 `scan-subject.json` 中的已验证身份集合，核对：

```bash
docker image inspect '<scan-subject.image_ref>' --format '{{.Id}}'
```

经典 Docker 的实际 ImageID 应等于 canonical config `image_id`；Docker 29 containerd 的 ImageID/Descriptor 可等于 `manifest_digest`。两者都必须属于 Security gate 已验证集合。

同时检查 OCI 版本标签：

```bash
docker image inspect '<scan-subject.image_ref>' \
  --format '{{ index .Config.Labels "org.opencontainers.image.version" }}'
```

必须等于当前 `APP_VERSION`。

## 6. Retag 与推送 Registry

这里只允许 retag/load 后的 exact image，禁止执行 build：

```bash
docker tag '<scan-subject.image_ref>' \
  'registry.example.com/zhongshu-lead-platform:1.2.5'

docker push 'registry.example.com/zhongshu-lead-platform:1.2.5'
```

推送完成后获取 registry 返回的 manifest digest，并形成最终不可变引用：

```text
registry.example.com/zhongshu-lead-platform:1.2.5@sha256:<registry-manifest-digest>
```

将该值写入生产 `.env` 的 `APP_IMAGE`。

## 7. Registry 回拉复核

在实际部署主机同步第 3 节的证据目录，并重新绑定同一个 run。

复核：

- OCI `org.opencontainers.image.version == APP_VERSION`；
- 镜像可正常 inspect；
- 回拉镜像的 ImageID、Descriptor 与可用的 config descriptor 必须落在候选 artifact 的已验证身份集合内，config descriptor 必须等于 canonical `image_id`；
- 以下命令必须通过：

```bash
set -euo pipefail
export SECURITY_RUN_ID='<已验证的 main push Security Analysis run id>'
export REPO_ROOT="$(git rev-parse --show-toplevel)"
export PROMOTION_DIR='<第 3 节生成并同步的绝对证据目录>'
test -f "$PROMOTION_DIR/candidate/scan-subject.json"

docker pull 'registry.example.com/zhongshu-lead-platform:1.2.5@sha256:<digest>'
python3 -I "$REPO_ROOT/scripts/verify_production.py" \
  --env-file "$REPO_ROOT/.env" \
  --require-image-digest \
  --require-image-inspect \
  --scan-subject "$PROMOTION_DIR/candidate/scan-subject.json"
```

如果 registry 回拉后的镜像内容/配置异常，停止发布并回到 candidate artifact，不允许“现场重建修一下”。

## 8. 发布证据归档

至少归档：

- main commit SHA；
- Security Analysis run ID；
- GitHub API 原始 run/workflow/artifact JSON；
- `security-promotion-source.json` 及其中的 candidate/evidence artifact ID；
- `scan-subject.json`；
- archive SHA-256；
- Docker ImageID；
- `security-gate.json`；
- `waivers-policy.json` 及其 SHA-256；
- Trivy JSON；
- CycloneDX SBOM；
- Semgrep scanner/rules identity；
- registry immutable `tag@sha256:digest`；
- 晋级执行人、时间和审批记录。

## 9. NO-GO

以下任一情况禁止晋级：

- 使用 PR artifact 直接生产发布；
- 使用 `workflow_dispatch` 或非 `main` push 的 artifact；
- 未先通过 GitHub API 元数据与 `check_security_promotion_source.py` 绑定真实 run/workflow/artifact ID；
- `security-gate.json` 缺少可信来源字段，或 event/ref/candidate/policy/waiver digest 不匹配；
- candidate artifact 与 security evidence 不是同一个 run；
- tar SHA-256 不匹配；
- Docker ImageID 不匹配；
- security gate 非 valid；
- 有未豁免 HIGH/CRITICAL/ERROR；
- waiver 已过期；
- candidate artifact 已丢失但试图手工 rebuild；
- registry 推送后无法用不可变 digest 回拉/验证。
