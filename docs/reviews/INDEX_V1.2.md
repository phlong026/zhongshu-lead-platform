# V1.2 代码评审与可追溯性索引

本索引覆盖 V1.2 从需求冻结到 Sprint 6、正式 Release 以及 main 发布后的工程收口记录。`预评审/上下文` 仅表示评审准备，不等于通过；真实生产放行仍必须结合目标环境 Go/No-Go。

| 编号 | 记录 | 性质 | 当前结论 |
|---:|---|---|---|
| 38 | [V1.2 需求与规则基线](38-v1.2-requirements-baseline.md) | 需求基线 | 已冻结 |
| 39 | [T01 数据库基础](39-v1.2-t01-database-foundation.md) | 代码评审 | 通过 |
| 40 | [T02 工作日历](40-v1.2-t02-workday-calendar.md) | 代码评审 | 通过 |
| 41 | [T03 状态机](41-v1.2-t03-state-machine.md) | 代码评审 | 通过 |
| 42 | [Sprint 1 客资供给后端](42-v1.2-sprint1-lead-supply-backend.md) | 代码评审 | 通过 |
| 43 | [Sprint 1 客资供给 UI](43-v1.2-sprint1-lead-supply-ui.md) | 代码评审 | 通过 |
| 44 | [Sprint 1 UI 自动评审修复](44-v1.2-sprint1-ui-review-fixes.md) | 整改记录 | 已关闭 |
| 45 | [Sprint 2 人工派发与领取](45-v1.2-sprint2-dispatch-claim-backend.md) | 代码评审 | 通过 |
| 46 | [Sprint 3 退回与核验](46-v1.2-sprint3-return-verification-backend.md) | 代码评审 | 通过 |
| 47 | [Sprint 4 供应奖励](47-v1.2-sprint4-supplier-rewards.md) | 代码评审 | 通过 |
| 48 | [Sprint 4 自动评审修复](48-v1.2-sprint4-auto-review-fixes.md) | 整改记录 | 已关闭 |
| 49 | [Sprint 5 H5/后台/通知/洞察集成](49-v1.2-sprint5-integration.md) | 集成评审 | 通过 |
| 50 | [Sprint 6 T30–T33 预评审](50-v1.2-sprint6-pre-review.md) | 预评审 | 不构成放行 |
| 51 | [Sprint 6 自动评审问题整改](51-v1.2-sprint6-auto-review-fixes.md) | 整改记录 | P1/P2 已关闭 |
| 52 | [Sprint 6 最终验证上下文](52-v1.2-sprint6-final-validation-context.md) | 验证上下文 | 不构成放行 |
| 53 | [Sprint 6 全维度综合终评](53-v1.2-sprint6-comprehensive-final-review.md) | 综合终评 | Release 门禁已完成 |
| 54 | [Main Release CI 收口](54-main-release-ci-v12.md) | 发布后工程收口 | 本 PR 验证中 |

## V1.2 最终代码发布证据

- PR #37：Sprint 6 主发布收口，全部 review thread 最终 resolved；
- PR #38：修复历史失败 migration checkpoint 重跑错误转绿问题，三组 PR 门禁全部 success；
- 最终 Release head：`4a6d0d0030f9b48d904704018cc4bbd2f35dd103`；
- Release CI run `31145037040`：`release-quality`、`release-postgres-migration`、`release-browser-smoke` 全部 success；
- Release OpenAPI、正式 package、PostgreSQL migration、browser smoke 四类 Artifact 均绑定最终 Release head；
- PR #39：`release/v1.2.0` 已合并到 `main`；
- `main` 发布 merge commit：`a2b3cafa7a0a570824824dbb5529242f7f1c374b`；
- `main` 与最终 Release head 文件树无差异。

## 放行边界

代码层 V1.2.0 已完成主线发布，但这不等于生产 Go-Live。真实服务号、正式 PostgreSQL/对象存储、生产 Secret、真实数据迁移与恢复演练、监控告警、法务隐私、3–5 家加盟商 UAT 和灰度仍必须按生产 Runbook 单独验收。
