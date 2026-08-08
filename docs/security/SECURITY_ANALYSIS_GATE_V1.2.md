# V1.2 SAST、镜像漏洞与供应链安全门禁

## 目标

H07 将现有 `pip-audit`、secret scan、pytest 安全负例之外的静态应用安全分析和生产镜像供应链风险转化为独立 CI 门禁。

本门禁不替代 H05 的权限/IDOR/并发攻击测试，也不替代 H12 的 Python 依赖临时漏洞豁免收口。

## 当前仓库能力边界

当前私有仓库未启用 GitHub Code Scanning / GitHub Code Security，因此不能把 CodeQL/SARIF 上传作为必需门禁，否则工作流会因仓库能力/授权而固定失败。

H07 当前采用：

1. Semgrep 作为 Python + JavaScript SAST；
2. Trivy 扫描通过根目录 `Dockerfile` 实际构建的生产镜像；
3. Trivy 生成 CycloneDX SBOM；
4. 仓库内 `check_security_gate.py` 统一判定 finding 与 waiver；
5. 所有扫描原始输出和判定结果作为 GitHub Actions artifact 保留 30 天。

当仓库未来启用 GitHub Code Security/Advanced Security 后，应在不移除现有门禁的前提下增加 CodeQL，并将 SARIF 结果纳入同一上线证据包。

## 固定工具

- Semgrep：由 `requirements-security.txt` 固定版本；
- Trivy：Security Analysis 工作流固定容器版本，不使用 floating `latest`；
- Trivy 扫描对象：当前提交构建出的真实生产 Docker 镜像。

固定版本升级必须走 PR、CI 和 Review，不允许在工作流中静默漂移。

## 阻断等级

### Semgrep

`extra.severity == ERROR` 的 finding 为阻断项。

WARNING/INFO 仍保留在原始 JSON 中供人工 Review，但不会单独使 CI 失败；若人工评审判定为 P0/P1/P2，仍按项目 Review 规则阻断合并。

### Trivy

生产镜像中的以下漏洞为阻断项：

- `CRITICAL`；
- `HIGH`。

无修复版本不等于自动豁免。未修复 High/Critical 仍需要结构化 waiver 或升级/替换依赖、基础镜像。

## Scanner 完整性

以下任一情况直接 fail-closed：

- Semgrep 命令执行失败；
- Semgrep JSON 报告内部含 scan errors；
- 生产 Docker 镜像构建失败；
- Trivy 工具拉取或镜像扫描失败；
- SBOM 生成失败；
- scanner exit-code 证据缺失；
- JSON 证据缺失或损坏；
- waiver registry 结构无效或存在过期 waiver。

不能通过 `continue-on-error` 把扫描器异常当成安全通过。

## Waiver 规则

统一登记在：

`security/waivers.json`

每条 waiver 必须包含：

- `scanner`：`semgrep` 或 `trivy`；
- `id`：Semgrep `check_id` 或 CVE/GHSA 等 Trivy VulnerabilityID；
- `scope`：Semgrep 文件路径或 Trivy package name，也可明确使用 `*`；
- `reason`：为何当前不能立即修复；
- `owner`：负责收口的人/角色；
- `expires_on`：ISO `YYYY-MM-DD`。

规则：

1. scanner + id + scope 必须匹配才生效；
2. 过期 waiver 即使当前 finding 已消失，也会使 CI 失败，要求删除或重新评审；
3. 重复 waiver 视为配置错误；
4. 不允许永久 waiver；
5. 新增/延期 waiver 必须在 PR Review 中明确解释补偿控制和修复截止日期。

## 证据包

Security Analysis artifact 至少包含：

- `semgrep.json`；
- `semgrep-console.txt`；
- `semgrep-exit-code.txt`；
- `image-build.txt`；
- `image-build-exit-code.txt`；
- `trivy-image.json`；
- `trivy-console.txt`；
- `trivy-exit-code.txt`；
- `sbom.cdx.json`；
- `security-gate.json`。

即使扫描失败，工作流也要尽可能保留已生成的失败证据，然后由统一 gate 返回失败。

## 与现有 CI 的关系

- Main Release Verification：pytest、coverage、pip-audit、secret scan、OpenAPI、JS check、PostgreSQL migration；
- Security Analysis：Semgrep SAST、生产镜像 Trivy、SBOM、通用 security waiver；
- 两者必须同时通过才能视为代码层灰度候选。

## 上线规则

以下任一情况为 NO-GO：

- Security Analysis 未运行或失败；
- 存在未豁免的 Semgrep ERROR；
- 存在未豁免的 Trivy HIGH/CRITICAL；
- 存在过期 waiver；
- 当前生产候选镜像没有对应 SBOM；
- PR 仍有未解决 P0/P1/P2 Review finding。
