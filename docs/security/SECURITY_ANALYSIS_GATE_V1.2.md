# V1.2 SAST、镜像漏洞与供应链安全门禁

## 目标

H07 将现有 `pip-audit`、secret scan、pytest 安全负例之外的静态应用安全分析和生产镜像供应链风险转化为独立 CI 门禁。

本门禁不替代 H05 的权限/IDOR/并发攻击测试，也不替代 H12 的 Python 依赖临时漏洞豁免收口。

## 当前仓库能力边界

当前私有仓库未启用 GitHub Code Scanning / GitHub Code Security，因此不能把 CodeQL/SARIF 上传作为必需门禁，否则工作流会因仓库能力/授权而固定失败。

H07 当前采用：

1. Semgrep 官方 scanner 镜像以 linux/amd64 immutable digest 固定，作为 Python + JavaScript SAST 执行主体；
2. Semgrep 官方 `semgrep-rules` 仓库固定到已验证 commit `40b8c63f75dc7c22c8a77482d73bfb864b146f7e`，运行时不再使用可变 Registry `p/...` 配置；
3. SAST 仅加载当前技术栈相关安全规则目录：Python lang / SQLAlchemy / FastAPI / boto3 / cryptography / JWT，以及 JavaScript lang / browser / Express / audit；
4. 项目源码与 Semgrep 规则目录均只读挂载，scanner 只获得预创建 `semgrep.json` 单文件写权限；
5. Semgrep 后执行 Git worktree integrity gate，scanner 若修改 tracked 或非忽略文件则立即失败；
6. 根目录 `Dockerfile` 构建真实生产候选镜像；
7. `docker save` 将候选镜像冻结为 tar archive，并记录 Docker ImageID 与 archive SHA-256；
8. Trivy 使用不可变 digest 固定的官方 scanner 镜像，对冻结 tar 执行漏洞扫描和 CycloneDX SBOM 生成；
9. Trivy 不挂载 `/var/run/docker.sock`，输入 tar 只读，单次容器仅能写一个预创建输出文件；
10. 仓库内 `check_security_gate.py` 统一校验 scanner schema、scan subject、SBOM、finding 与 waiver；
11. 所有扫描原始输出和判定结果作为 GitHub Actions artifact 保留 30 天。

当仓库未来启用 GitHub Code Security/Advanced Security 后，应在不移除现有门禁的前提下增加 CodeQL，并将 SARIF 结果纳入同一上线证据包。

## 固定工具与规则

### Semgrep scanner

Security Analysis 使用：

`semgrep/semgrep@sha256:a8298d1c09c84b9a0bbc75ec915e37023fc4657360b6dbfa645261d2353a366c`

该 digest 对应 H07 评审时确认的 Semgrep 1.172.0 linux/amd64 发布镜像。禁止改回 floating tag 或动态 `pip install semgrep` 作为 CI scanner 来源。

### Semgrep rules

规则来源固定为官方仓库 commit：

`40b8c63f75dc7c22c8a77482d73bfb864b146f7e`

工作流：

- 仅 fetch 该 commit；
- checkout detached HEAD；
- `rev-parse HEAD` 必须精确等于固定 SHA；
- 执行 `git fsck --strict`；
- 将规则 commit 与 tree hash写入安全 evidence；
- 不使用 `p/security-audit`、`p/owasp-top-ten` 等运行时可变 Registry config。

当前固定规则目录：

- `python/lang/security`；
- `python/sqlalchemy/security`；
- `python/fastapi/security`；
- `python/boto3/security`；
- `python/cryptography/security`；
- `python/jwt/security`；
- `javascript/lang/security`；
- `javascript/browser/security`；
- `javascript/express/security`；
- `javascript/audit`。

### Production base

生产 Dockerfile 使用 Python Bookworm base 的 linux/amd64 immutable digest，避免同一 tag 后续漂移改变扫描对象。

### Trivy

工作流使用：

`aquasec/trivy@sha256:85e87be1a96459c38a4eea47dc64eb2d342bb14cd4b4cef96adcf6ff03378b7c`

该 digest 对应 H07 评审时确认的 Trivy 0.70.0 linux/amd64 镜像。

Trivy 扫描对象是当前提交构建后冻结的 `app-image.tar`，不从 registry 或 Docker socket 重新解析另一个同名镜像。

任何 scanner、rule commit、base digest、Trivy digest 升级必须走 PR、CI 和 Review，不允许在工作流中静默漂移。

## 阻断等级

### Semgrep

`extra.severity == ERROR` 的 finding 为阻断项。

WARNING/INFO 仍保留在原始 JSON 中供人工 Review，但不会单独使 CI 失败；若人工评审判定为 P0/P1/P2，仍按项目 Review 规则阻断合并。

### Trivy

生产镜像中的以下漏洞为阻断项：

- `CRITICAL`；
- `HIGH`。

无修复版本不等于自动豁免。未修复 High/Critical 仍需要升级/替换基础镜像或结构化、精确、短期 waiver。

## Scanner 与证据完整性

以下任一情况直接 fail-closed：

- Semgrep scanner 镜像拉取或执行失败；
- Semgrep JSON 缺少 `results` / `errors` 数组；
- Semgrep result 结构不符合预期或 report 内含 scan errors；
- 固定 Semgrep rule commit 无法精确 fetch / checkout / `fsck`；
- 固定安全规则目录缺失；
- Semgrep/SAST tooling 修改 checkout 的 tracked 或非忽略文件；
- 生产 Docker 镜像构建或 `docker save` 失败；
- image archive SHA-256 与 `scan-subject.json` 不一致；
- Docker ImageID 不是完整 `sha256:<64 lowercase hex>`；
- Trivy 工具拉取或 tar archive 扫描失败；
- Trivy JSON 的 SchemaVersion / ArtifactName / ArtifactType / Results 结构异常；
- SBOM 缺失、JSON 损坏或不是 CycloneDX；
- SBOM `components` 为空；
- SBOM 未声明 `aquasecurity/trivy` 0.70.0 为生成工具；
- SBOM `metadata.component` 不是 container；
- SBOM 的 Trivy `Reference` / `ImageID` 与同一次 scan subject 不一致；
- scanner exit-code 证据缺失；
- waiver registry 结构无效、存在过期/未来创建/超长期/重复 waiver。

不能通过 `continue-on-error`、空 JSON、空 SBOM 或 scanner/tooling 异常把安全分析误判为通过。

## Waiver 规则

统一登记在：

`security/waivers.json`

每条 waiver 必须包含：

- `scanner`：`semgrep` 或 `trivy`；
- `id`：Semgrep `check_id` 或 Trivy VulnerabilityID；
- `scope`：**精确** Semgrep 文件路径或 Trivy package name；
- `reason`：为何当前不能立即修复；
- `owner`：负责收口的人/角色；
- `created_on`：ISO `YYYY-MM-DD`；
- `expires_on`：ISO `YYYY-MM-DD`。

规则：

1. scanner + id + scope 必须完全匹配才生效；
2. `scope: "*"` 明确禁止，不能让一个历史例外覆盖未来新增文件/包；
3. 单条 waiver 最长 30 天；
4. `created_on` 不能在未来，`expires_on` 不能早于 `created_on`；
5. 过期 waiver 即使当前 finding 已消失，也会使 CI 失败，要求删除或重新评审；
6. 重复 waiver 视为配置错误；
7. 新增/延期 waiver 必须在 PR Review 中解释补偿控制和修复任务；延期通过更新 `created_on` / `expires_on` 重新开始一个不超过 30 天的评审周期。

## 当前受控例外

H07 首次基线中仅允许精确列出的短期例外：

- `scripts/verify_production.py` 的 Semgrep subprocess taint rule：该脚本通过 argv list、`shell=False` 调用 Docker，使用文件级精确 scope 并在 30 天内重新评审；
- `cryptography` 的单一 Trivy CVE：仅作为 H12 #61 的短期隔离例外，H12 必须升级修复版本并删除 waiver。

禁止把基础镜像的一组 High/Critical 用全局 scope 批量压制；应优先调整基础镜像或逐项形成有明确责任的短期处理。

## 证据包

Security Analysis artifact 至少包含：

### Semgrep

- `semgrep-image-ref.txt`；
- `semgrep-pull.txt`；
- `semgrep-version.txt`；
- `semgrep-rules-commit.txt`；
- `semgrep-rules-tree.txt`；
- `semgrep.json`；
- `semgrep-console.txt`；
- `semgrep-exit-code.txt`。

### Production image / Trivy / SBOM

- `image-build.txt`；
- `image-build-exit-code.txt`；
- `scan-subject.json`；
- `trivy-image-ref.txt`；
- `trivy-pull.txt`；
- `trivy-image.json`；
- `trivy-console.txt`；
- `trivy-exit-code.txt`；
- `sbom.cdx.json`；
- `security-gate.json`。

`app-image.tar` 只作为 runner 内瞬时扫描对象。统一 gate 校验 tar SHA-256 后删除该大文件，不把镜像 tar 重复上传为 Actions artifact；正式发布镜像仍通过不可变 registry digest 管理。

即使扫描失败，工作流也要尽可能保留已生成的失败证据，然后由统一 gate 返回失败。

## 与现有 CI 的关系

- Main Release Verification：pytest、coverage、pip-audit、secret scan、OpenAPI、JS check、PostgreSQL migration；
- Security Analysis：immutable Semgrep SAST + pinned rule snapshot、冻结生产镜像 Trivy、SBOM、结构化 security waiver；
- 两者必须同时通过才能视为代码层灰度候选。

## 上线规则

以下任一情况为 NO-GO：

- Security Analysis 未在真实 runner 上成功执行或失败；
- 存在未豁免的 Semgrep ERROR；
- 存在未豁免的 Trivy HIGH/CRITICAL；
- scanner/rules/SBOM/scan subject 证据结构或绑定校验失败；
- 存在过期、超期或通配 scope waiver；
- 当前生产候选镜像没有对应 CycloneDX SBOM；
- PR 仍有未解决 P0/P1/P2 Review finding。
