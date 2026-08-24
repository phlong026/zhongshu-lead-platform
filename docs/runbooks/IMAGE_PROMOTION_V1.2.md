# V1.2 绿色扫描镜像晋级与发布 SOP

## 1. 强制原则

生产发布不得重新构建已经通过 Security Analysis 的应用镜像。

唯一允许晋级的构建产物是：

- `main` 分支目标 commit 的 **post-merge Security Analysis** 成功 run；
- 该 run 生成的 `security-candidate-image-<run_id>` artifact；
- artifact 内的 `app-image.tar` 与 `scan-subject.json`。

PR 分支上的候选 artifact 只能用于评审/调试，不能直接作为生产来源。生产来源必须是合并后 `main` 相同提交再次真实通过 Security Analysis 后生成的 artifact。

如果 artifact 已过期，必须对**同一 main commit**重新运行 Security Analysis 生成新的、再次通过扫描的 candidate artifact。禁止在发布机、CI 外或另一个 commit 上执行 `docker build` 代替。

## 2. 为什么禁止重建

Docker build 可能受以下输入影响：

- package registry 当前状态；
- 传递依赖；
- 基础镜像内容；
- 构建器版本与网络返回；
- 上游资源变化。

即使 Dockerfile、requirements 和 Git commit 不变，重新 build 也不等价于“发布之前扫描过的那一组镜像字节”。H07 因此要求安全扫描通过后保存 exact image archive，再晋级该 archive。

## 3. 下载证据

从同一个成功的 `main` Security Analysis run 下载：

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
- `scan_subject.image_ref` / `image_id` / `archive_sha256` 存在；
- 所有 active waiver 仍在有效期内。

再核对 candidate artifact：

```bash
python - <<'PY'
import hashlib
import json
from pathlib import Path

subject = json.loads(Path('scan-subject.json').read_text(encoding='utf-8'))
actual = hashlib.sha256(Path('app-image.tar').read_bytes()).hexdigest()
expected = subject['archive_sha256']
assert actual == expected, (actual, expected)
print('archive sha256 verified:', actual)
print('expected image id:', subject['image_id'])
print('scanned image ref:', subject['image_ref'])
PY
```

SHA-256 不一致直接 `NO-GO`。

## 5. 加载 exact scanned image

```bash
docker load -i app-image.tar
```

然后读取 `scan-subject.json` 中的 `image_ref` 和 `image_id`，核对：

```bash
docker image inspect '<scan-subject.image_ref>' --format '{{.Id}}'
```

实际 ImageID 必须与 `scan-subject.image_id` 完全一致。

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
  'registry.example.com/zhongshu-lead-platform:1.2.1'

docker push 'registry.example.com/zhongshu-lead-platform:1.2.1'
```

推送完成后获取 registry 返回的 manifest digest，并形成最终不可变引用：

```text
registry.example.com/zhongshu-lead-platform:1.2.1@sha256:<registry-manifest-digest>
```

将该值写入生产 `.env` 的 `APP_IMAGE`。

## 7. Registry 回拉复核

在实际部署主机：

```bash
docker pull 'registry.example.com/zhongshu-lead-platform:1.2.1@sha256:<digest>'
```

复核：

- OCI `org.opencontainers.image.version == APP_VERSION`；
- 镜像可正常 inspect；
- 回拉镜像的 `docker image inspect ... '{{.Id}}'` 必须与候选 artifact 中 `scan-subject.image_id` 完全一致；
- 以下命令必须通过：

```bash
python scripts/verify_production.py \
  --env-file .env \
  --require-image-digest \
  --require-image-inspect \
  --scan-subject scan-subject.json
```

如果 registry 回拉后的镜像内容/配置异常，停止发布并回到 candidate artifact，不允许“现场重建修一下”。

## 8. 发布证据归档

至少归档：

- main commit SHA；
- Security Analysis run ID；
- candidate artifact ID；
- `scan-subject.json`；
- archive SHA-256；
- Docker ImageID；
- `security-gate.json`；
- Trivy JSON；
- CycloneDX SBOM；
- Semgrep scanner/rules identity；
- registry immutable `tag@sha256:digest`；
- 晋级执行人、时间和审批记录。

## 9. NO-GO

以下任一情况禁止晋级：

- 使用 PR artifact 直接生产发布；
- candidate artifact 与 security evidence 不是同一个 run；
- tar SHA-256 不匹配；
- Docker ImageID 不匹配；
- security gate 非 valid；
- 有未豁免 HIGH/CRITICAL/ERROR；
- waiver 已过期；
- candidate artifact 已丢失但试图手工 rebuild；
- registry 推送后无法用不可变 digest 回拉/验证。
