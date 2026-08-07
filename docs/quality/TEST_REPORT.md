# 众墅之家客资平台 V1.2 测试与质量报告

- 发布候选版本：`V1.2.0`
- 报告日期：2026-08-07
- 代码基线：V1.2 Sprint 0–6 / `release/v1.2.0`
- 目标生产环境：Python 3.12、PostgreSQL 16、私有 S3/COS/OSS、Nginx HTTPS、API + Scheduler
- 最终自动化证据：以 `.github/workflows/v12-release-ci.yml` 在发布分支合并提交上的执行记录与 Artifact 为唯一权威结果

## 1. 质量结论边界

V1.2 的代码质量体系已从早期 SQLite/P0 单层测试升级为三层正式发布门禁：

1. `release-quality`：依赖一致性、依赖漏洞扫描、全量 Pytest、OpenAPI、JavaScript、密钥扫描、Python 编译、空白检查、SQLite 迁移循环，并从完整 Git 历史构建最终 V1.2.0 交付包；
2. `release-postgres-migration`：PostgreSQL 16 上从 V1.0.1 历史夹具升级到 V1.2、手机号指纹回填、数据语义对账、关键并发/幂等约束验证、降级和再升级；
3. `release-browser-smoke`：真实 Chromium 中的桌面管理后台和移动 H5 登录、加载、console/pageerror、关键组件与截图证据。

本文件描述代码层测试范围和发布门禁，不伪造尚未发生的生产结果。正式版本只有在发布分支对应三组 Actions 均成功后，才可作为“代码可进入目标环境 UAT/灰度”的证据；真实服务号、生产数据库、对象存储、恢复演练、业务 UAT 和灰度仍需现场 Go/No-Go。

## 2. 业务闭环覆盖

自动测试与服务级评审覆盖 V1.2 主链路：

```text
平台手工录入 / 供应商 H5 供给
→ HMAC 手机号去重（90/180/365 天）
→ 供应资料初审
→ READY_DISPATCH
→ 平台人工候选筛选与派发
→ 加盟商领取、单次扣分、手机号解锁
→ 跟进
→ 3 个工作日内截图或录音退回申诉
→ RETURN_VERIFY 后置电销事实核验
→ 平台终审、返分/驳回
→ 供应奖励观察、冻结、取消、结算或异常冲正
→ 通知、报表、审计与业务 ID 追踪
```

正常客资不执行前置电销；V1.2 不提供自动派发、随机派发、抢单、自供自领或在线支付。

## 3. 自动化测试矩阵

| 维度 | 主要验证 |
|---|---|
| 数据迁移 | V1.0.1 基线、Alembic upgrade、手机号指纹 dry-run/回填、检查点、断点续跑、错误阻断、downgrade/re-upgrade |
| PostgreSQL | PostgreSQL 16 服务、真实 DDL、有效派发部分唯一索引、积分/退回/奖励唯一约束、迁移后验证 JSON、账务语义对账 |
| 客资供给 | 平台录入、供应商上传、公司能力、服务区域、审核状态、去重结论 |
| 人工派发 | 仅人工入口、候选资格、自供禁止、区域匹配、接收历史去重、积分可用额、有效派发唯一约束 |
| 领取扣分 | 行锁、状态重检、过期校验、单次扣分、幂等流水、手机号领取后解锁 |
| 退回申诉 | 3 个工作日、截图或录音至少一项、任务分配/领取/提交、终审、返分幂等、奖励冻结/取消；兼容 V1.0.x `RETURN_REQUEST` 与 V1.2 `V12_RETURN_REFUND` 两种合法历史流水语义 |
| 供应奖励 | 观察期、活动申诉冻结、有界批结算、坏行隔离、奖励结算、异常冲正、规则快照 |
| 积分账务 | 账户余额、不可变流水、`balance_after` 序列、领取/返分/奖励/冲正业务关联语义 |
| RBAC/隐私 | 公司隔离、角色权限、手机号脱敏、财务字段限制、审计快照脱敏、深链越权 |
| 外部集成 | 飞书启用开关 fail-closed、分页/token/回写契约；微信生产 mock 禁止与通知 Outbox 契约 |
| 对象存储 | 本地私有测试存储、S3 配置校验、自定义 endpoint HTTPS、安全访问契约 |
| 生产配置 | HTTPS、CORS、Trusted Hosts、独立密钥、禁止 Demo、禁止隐式 schema 创建、不可变镜像 tag/digest/OCI 版本一致性、Compose 凭据 URL 编码 |
| 浏览器 | 1440×900 管理后台、390×844 H5、登录、关键 KPI/导航、可见错误、console error、pageerror |
| 发布包 | 完整 Git history、跟踪文件白名单、真实 `.env` 排除、Manifest 唯一、校验和、Runbook/评审/测试/安全审计资料强制齐全 |

## 4. V1.2 数据迁移与账务对账门禁

`reconcile_v12.py` 不只检查“外键非空”，还验证业务语义：

- 所有历史客资均有独立 HMAC-SHA256 `phone_fingerprint`；
- 迁移检查点为 `COMPLETED` 且错误数为 0；
- 不存在未知历史状态；
- 同一客资最多一个有效派发单；
- 每个积分账户余额等于流水 delta 汇总，最新 `balance_after` 与账户一致；
- 已结算/已冲正供应奖励的流水公司、业务类型、业务 ID、流水类型、金额和关联原流水必须正确；
- 已批准退回的返分流水必须与公司、退回 ID、返分金额及原领取扣分流水完全对应；V1.0.x 的 `RETURN_REQUEST` 与 V1.2 的 `V12_RETURN_REFUND` 作为明确白名单历史语义处理，其余关联字段仍严格一致；
- 证据对象键、64 位 SHA-256 和文件大小完整。

只要任一语义不一致，生产 reconciliation 返回非零并触发 `NO-GO`。

## 5. 生产配置与安全门禁

最终 `preflight_v12.py --compose-database` 同时验证：

- `APP_ENV=production`、`APP_VERSION=1.2.x`；
- PostgreSQL 而非 SQLite；
- JWT、字段加密、旧手机号哈希、V1.2 手机指纹四类密钥满足长度要求，且手机号两类 HMAC 密钥相互独立；
- 微信/飞书开发 mock 关闭；
- 正式 CORS 与 Trusted Hosts；
- `AUTO_CREATE_SCHEMA=false`、`SEED_DEMO=false`；
- 私有对象存储配置；
- `APP_IMAGE` 显式版本 tag 与 `APP_VERSION` 完全相同；
- 正式 Go/No-Go 使用 `@sha256:` digest；
- 实际拉取镜像的 OCI `org.opencontainers.image.version` 与 `APP_VERSION` 相同；
- API/Scheduler 与宿主机校验使用一致的 PostgreSQL URL 编码规则；
- Alembic revision 和数据 reconciliation 在生产 Compose 网络中连接真实 `db:5432`，禁止误读宿主机 SQLite；
- Preflight 输出对数据库 URL、口令、Token 和访问密钥脱敏。

## 6. 浏览器与发布证据

浏览器任务使用 Playwright Chromium：

- 桌面 1440×900：管理员登录、V1.2 运营台、KPI 加载；
- 移动 390×844：加盟商登录、V1.2 H5 工作台、头部与导航；
- 任一应用 `console error`、`pageerror` 或显式错误区域均使任务失败；
- 任务无论成功或失败均尽量保存 JSON 报告、服务器日志和已经生成的截图。

发布分支 Artifact 应至少包含：

- `v12-release-openapi-*`：冻结的运行时 OpenAPI；
- `v12-release-package-*`：V1.2.0 完整源码 ZIP、完整 Git 提交历史 bundle、完整交付包与 SHA-256 校验文件；
- `v12-release-postgres-migration-*`：V1.0.1 基线 + V1.2 PostgreSQL 验证/约束 JSON；
- `v12-release-browser-smoke-*`：桌面/移动截图、浏览器报告、服务器日志。

PR 阶段 `full-quality` 也使用 `fetch-depth: 0` 构建 `V1.2.0-rc` 完整交付包，提前验证发布脚本、Git bundle、文档齐备和校验和逻辑。

## 7. 已有历史 CI 证据

Sprint 5 之前的合并已由当时发布分支 CI 验证。其中可追溯的重要记录包括：

- Sprint 4 PR #33 合并后 Release CI：`31100059902`；
- Sprint 5 PR #34 合并后 Release CI：`31104455574`。

Sprint 6 改变了迁移、生产配置、浏览器和发布门禁，因此历史 CI 不能替代 Sprint 6 最终发布分支三组新门禁。

## 8. 仍必须在目标环境完成的验证

以下项目不属于代码仓库自动测试，必须现场执行：

- 企业认证服务号的 OAuth、网页授权域名、真实通知/失败重试和深链；
- iOS/Android 不同微信版本的 H5、文件选择和弱网行为；
- 真实飞书应用（启用时）的权限、限流、分页和回写；
- 正式 PostgreSQL 数据全量迁移、实际锁等待、数据库大小和迁移耗时；
- 正式 S3/COS/OSS 的桶策略、版本、生命周期、上传和授权访问；
- PostgreSQL + 对象存储 + 密钥的联合备份恢复演练；
- 3–5 家真实加盟商 UAT 与 24–72 小时灰度；
- 隐私、录音授权、数据保留和相关法务确认；
- 生产告警故障注入与值班响应演练。

## 9. 发布判定

代码层 `GO` 的必要条件：

1. 最新 Codex/人工综合评审无未解决 P0/P1/P2；
2. `release-quality` 成功并产生 `v12-release-openapi-*` 与 `v12-release-package-*`；
3. `release-postgres-migration` 成功并产生完整迁移/约束证据；
4. `release-browser-smoke` 成功并产生浏览器截图/报告；
5. 所有发布 Artifact 可下载且内容完整；
6. 最终交付包 SHA-256 校验通过。

满足以上条件仅表示“代码可进入生产环境最终 UAT/灰度”，不等于可以直接向全部加盟商开放。
