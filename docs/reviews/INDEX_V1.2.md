# V1.2 代码评审与可追溯性索引

本索引覆盖 V1.2 从需求冻结到 Sprint 6 上线前收口的正式评审记录。`预评审/上下文` 仅表示评审准备，不等于通过；最终生产放行必须结合最新 Codex 终审、Release CI 与目标环境 Go/No-Go。

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
| 51 | [Sprint 6 自动评审问题整改](51-v1.2-sprint6-auto-review-fixes.md) | 整改记录 | 已知 P1/P2 已关闭，等待最新终审 |
| 52 | [Sprint 6 最终验证上下文](52-v1.2-sprint6-final-validation-context.md) | 验证上下文 | 不构成放行 |
| 53 | [Sprint 6 全维度综合终评](53-v1.2-sprint6-comprehensive-final-review.md) | 综合终评 | 条件通过，等待最新 Codex + Release CI |

## Sprint 6 终评必须关联的质量证据

- PR #37 最新稳定 head；
- 最新 Codex review：无未解决 P0/P1/P2；
- `release-quality`；
- `release-postgres-migration`；
- `release-browser-smoke`；
- OpenAPI Artifact；
- PostgreSQL V1.0.1 基线 + V1.2 验证 JSON Artifact；
- Chromium 桌面/移动截图、浏览器 JSON 和服务器日志 Artifact；
- `docs/quality/TEST_REPORT.md`；
- `docs/quality/SECURITY_AUDIT.md`；
- `docs/runbooks/V1.2_GO_NO_GO.md`。

## 放行边界

代码层最终通过只表示版本可以进入目标环境 UAT/灰度。真实服务号、正式 PostgreSQL/对象存储、备份恢复、监控告警、法务隐私、3–5 家加盟商 UAT 和 24–72 小时灰度必须另行签字。
