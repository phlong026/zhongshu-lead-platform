# V1.2 SAST、镜像漏洞与供应链安全门禁

## 目标

H07 将现有 `pip-audit`、secret scan、pytest 安全负例之外的静态应用安全分析和生产镜像供应链风险转化为独立 CI 门禁。

本门禁不替代 H05 的权限/IDOR/并发攻击测试，也不替代 H12 的 Python 依赖临时漏洞豁免收口。

## 当前仓库能力边界

当前私有仓库未启用 GitHub Code Scanning / GitHub Code Security，因此不能把 CodeQL/SARIF 上传作为必需门禁，否则工作流会因仓库能力/授权而固定失败。

H07 当前采用：

1. 工作流使用的 `actions/checkout`、`actions/setup-python`、`actions/upload-artifact` 均固定到完整 commit SHA，避免可移动大版本 tag 成为 CI 信任链缺口；
2. PR 使用 `pull_request_target` 执行受保护 base 分支的 workflow；base policy 与候选 head 分目录 checkout，validator 和 waiver registry 均取自 base，候选仅作为只读扫描/镜像构建输入；
3. Semgrep 官方 scanner 镜像以 linux/amd64 immutable digest 固定，作为 Python + JavaScript SAST 执行主体；
4. Semgrep 官方 `semgrep-rules` 仓库固定到 verified commit `40b8c63f75dc7c22c8a77482d73bfb864b146f7e`，运行时不再使用可变 Registry `p/...` 配置；
5. SAST 仅加载当前技术栈相关安全规则目录：Python lang / SQLAlchemy / FastAPI / boto3 / cryptography / JWT，以及 JavaScript lang / browser / Express / audit；
6. 项目源码与 Semgrep 规则目录均只读挂载，scanner 只获得预创建 `semgrep.json` 单文件写权限；
7. 显式关闭 Semgrep 默认 ignore 文件，再用工作流内 `.git` / `dist` / `storage` 排除项限定边界，确保源码根目录内所有 Python/JavaScript（包括测试目录）进入扫描清单；
8. Semgrep 后执行 Git worktree integrity gate，scanner 若修改 tracked 或非忽略文件则立即失败；
9. 根目录 `Dockerfile` 构建真实生产候选镜像；
10. `docker save` 将候选镜像冻结为 tar archive，并记录 Docker ImageID 与 archive SHA-256；
11. gate 同时验证 legacy Docker archive 与 Docker Desktop 生成的 OCI archive：目标 tag 必须唯一，所有 descriptor/blob digest 与 size 必须闭环，scanner 使用的 config 必须可从 subject ImageID 到达；
12. Trivy 使用不可变 digest 固定的官方 scanner 镜像，对冻结 tar 执行漏洞扫描和 CycloneDX SBOM 生成；
13. Trivy 不挂载 `/var/run/docker.sock`，输入 tar 只读，单次容器仅能写一个预创建输出文件；
14. 受保护 base 中的 `check_security_gate.py` 统一校验 scanner schema、Docker archive identity、Trivy Metadata、完整包清单、SBOM、finding 与 waiver；
15. 所有扫描原始输出和判定结果作为 GitHub Actions artifact 保留 30 天。

当仓库未来启用 GitHub Code Security/Advanced Security 后，应在不移除现有门禁的前提下增加 CodeQL，并将 SARIF 结果纳入同一上线证据包。

## 固定工具与规则

### GitHub Actions

Security Analysis 的第三方 Actions 固定为：

- `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`（v4.2.2）；
- `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065`（v5.6.0）；
- `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02`（v4.6.2）。

禁止改回 moving tag；升级必须同时复核官方 release、完整 SHA 和工作流权限。

### PR 策略信任边界

`pull_request` 会让候选分支同时控制 workflow、validator 与 policy，不足以形成安全门禁。H07 改用 `pull_request_target`，只执行 base 分支已有的 workflow，并做两次无凭据持久化的 checkout：

- `policy/` 固定到 PR base SHA；
- `candidate/` 固定到 PR head SHA；
- Semgrep 与 Docker build 仅处理 `candidate/`；
- gate 由 `policy/scripts/check_security_gate.py` 执行，并只接受 `policy/security/waivers.json`；
- token 权限保持 `contents: read`，两个 checkout 均设置 `persist-credentials: false`。

候选 PR 因此不能通过修改 workflow、validator 或 waiver 自行给出绿灯。waiver policy 变更属于受保护策略变更，需要独立提升审查/合并，不能在同一个候选 PR 中即时生效。H07 当前 PR 是该策略的 bootstrap：base 尚无这份 workflow，故以全新 Linux Git 快照的本地等价执行和独立 Review 完成首次验收；合并后的 main push 及后续 PR 才由受保护策略直接执行。

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
- 将 rules commit 与 tree hash 写入安全 evidence；
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

Semgrep 自带的默认 ignore 会跳过测试目录，不能仅依赖 `--include` 重新纳入。工作流因此固定使用 `--x-ignore-semgrepignore-files`，再由明确的 `--exclude` 控制非源码目录。统一 gate 会递归计算源码根目录内应扫的 `.py` / `.js` 清单，并要求报告中的 scanned path 集合完整覆盖该清单；漏扫任何一个测试或脚本均 fail-closed。

### Production base

生产 Dockerfile 使用 Python Bookworm base 的 linux/amd64 immutable digest，避免同一 tag 后续漂移改变扫描对象。

### Trivy

工作流使用：

`aquasec/trivy@sha256:85e87be1a96459c38a4eea47dc64eb2d342bb14cd4b4cef96adcf6ff03378b7c`

该 digest 对应 H07 评审时确认的 Trivy 0.70.0 linux/amd64 镜像。

Trivy 扫描对象是当前提交构建后冻结的 `app-image.tar`，不从 registry 或 Docker socket 重新解析另一个同名镜像。

### Archive 模式身份语义

Trivy 官方 archive 实现中，`--input /tmp/app-image.tar` 的 artifact name 是 scanner 内部输入路径 `/tmp/app-image.tar`，不是原 Docker tag。因此 H07 不再错误要求 `ArtifactName == image_ref`。

身份闭环改为：

1. `scan-subject.json` 记录预扫描的 `image_ref`、完整 Docker `ImageID`、archive SHA-256；
2. gate 自己打开 Docker tar 的 `manifest.json`，确认 RepoTags 精确包含 `image_ref`；
3. legacy archive 要求 manifest `Config` 等于 subject ImageID 对应的 config 文件名，并校验 config 内容 digest；
4. OCI archive 要求 `index.json` 唯一引用 subject ImageID，递归校验 index / manifest / config descriptor 的 digest 与 size，并要求 `manifest.json` 的 config blob 可由 subject ImageID 到达；
5. gate 将上述闭环解析出的 config digest 作为 Trivy archive identity；legacy 模式下它与 subject ImageID 相同，OCI index 模式下允许二者按 OCI 语义不同；
6. Trivy JSON `ArtifactName` 必须等于固定 scanner archive path `/tmp/app-image.tar`；
7. Trivy JSON `Metadata.ImageID` 必须等于 gate 解析出的 Trivy archive identity；
8. Trivy JSON `Metadata.RepoTags` 必须包含 subject image_ref；
9. CycloneDX `metadata.component.name` 必须等于 `/tmp/app-image.tar`；
10. SBOM properties 中 `Reference`、`RepoTag` 必须各自精确且唯一地等于 subject image_ref，`ImageID` 必须精确且唯一地等于 gate 解析出的 Trivy archive identity。
11. Trivy Debian/Python `Packages[].Identifier.PURL` 联合集合必须与 CycloneDX 所有 `library` component 的 `purl` 集合精确相等；缺失、额外或重复 package 均失败。

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
- Docker archive `manifest.json` 缺失/损坏/存在目标 tag 歧义；
- Docker archive RepoTags、legacy config digest 或 OCI descriptor/digest/size/reachability 与 subject identity 不一致；
- Trivy 工具拉取或 tar archive 扫描失败；
- Trivy JSON 的 SchemaVersion / archive ArtifactName / ArtifactType / Metadata.ImageID / Metadata.RepoTags / Results 结构异常；
- SBOM 缺失、JSON 损坏或不是 CycloneDX；
- SBOM `components` 为空；
- SBOM 未声明 `aquasecurity/trivy` 0.70.0 为唯一生成工具；
- SBOM `metadata.component` 不是 container 或 component name 不是固定 archive path；
- SBOM 的 Trivy `Reference` / `RepoTag` / `ImageID` 不唯一或与同一次 scan subject 不一致；
- Trivy Debian/Python package PURL 清单与 SBOM library component PURL 清单不完全一致；
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

H07 latest-head 本地复刻扫描保留 31 个逐 occurrence 的短期例外：

- 6 个 Semgrep subprocess finding：覆盖 migration 测试和 3 个运维脚本的固定 argv 调用；均未启用 shell，并绑定精确规则、文件和行列 occurrence，最晚 2026-09-07 到期；
- 1 个 `cryptography 49.0.0` finding：绑定 H12 #61，固定版本为 50.0.0，2026-08-21 到期；
- 24 个 Debian Bookworm 系统包 finding：当前 pinned base 和同代可用更新均无修复版本，逐 CVE、package、版本和 Trivy target 精确登记，2026-08-21 到期。补偿控制包括非 root、drop capabilities、只读根文件系统，以及应用不调用对应 block-device、terminal、Perl/archive 等受影响路径；到期前必须重建/替换基础镜像并删除 waiver。

这些例外不是永久基线。禁止使用全局 scope 批量压制；新增 finding 不会被现有 waiver 覆盖，任何延期都必须重新评审并保持不超过 30 天。

## 浏览器动态 HTML 边界

完整 JavaScript SAST 暴露了历史页面大量动态 `innerHTML` 写入。H07 将所有被阻断的动态 sink 收敛到同步加载的 `safe-html.js`：通过 inert `DOMParser` 建立 fragment，移除可执行标签、事件属性、`srcdoc` / `srcset`、危险 URL 与危险 style，再使用 `replaceChildren` / `replaceWith` 写入。业务表单、表格和下拉项保持可用；外链新窗口强制补 `noopener noreferrer`。7 个浏览器入口均要求先加载该边界，再加载业务脚本。

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

`app-image.tar` 在扫描期间是 runner 内瞬时对象。统一 gate 通过后，它与 `scan-subject.json` 作为独立的 `security-candidate-image-<run_id>` artifact 保留 7 天，供 exact-image 晋级；随后从 runner 工作目录删除，因此 30 天的常规安全 evidence artifact 不重复包含该大文件。正式发布仍按 `IMAGE_PROMOTION_V1.2.md` 将这份已扫描 archive 晋级为不可变 registry digest。gate 失败时不会生成候选镜像 artifact。

即使扫描失败，工作流也要尽可能保留已生成的失败证据，然后由统一 gate 返回失败。

## 与现有 CI 的关系

- Main Release Verification：pytest、coverage、pip-audit、secret scan、OpenAPI、JS check、PostgreSQL migration；
- Security Analysis：immutable Semgrep SAST + pinned rule snapshot、冻结生产镜像 Trivy、SBOM、结构化 security waiver；
- 两者必须同时通过才能视为代码层灰度候选。

GitHub Actions 因 Billing 无法启动 runner 时，必须在全新 Linux Git 快照上逐项等价执行 workflow 中的命令、固定镜像/规则、环境变量和 fail-closed gate。该本地结果用于当前 Hardening 验收，但不删除或降低 hosted workflow；Billing 恢复后仍应补跑 hosted CI。

## 上线规则

以下任一情况为 NO-GO：

- Security Analysis 未在 GitHub runner 或全新 Linux Git 快照的本地等价环境中成功执行，或执行失败；
- 存在未豁免的 Semgrep ERROR；
- 存在未豁免的 Trivy HIGH/CRITICAL；
- scanner/rules/Docker archive/SBOM/scan subject 证据结构或身份绑定校验失败；
- 存在过期、超期或通配 scope waiver；
- 当前生产候选镜像没有对应 CycloneDX SBOM；
- PR 仍有未解决 P0/P1/P2 Review finding。
