# 任务级代码评审索引

本目录保存从早期 P0/V1.0.x 到 V1.2 的任务级代码评审、整改、预评审和最终综合评审记录。不同版本的评审结论不能相互替代。

## 当前生产候选：V1.2

V1.2 的完整评审链请以以下专属索引为准：

- [V1.2 代码评审与可追溯性索引](INDEX_V1.2.md)
- [Sprint 6 自动评审问题整改](51-v1.2-sprint6-auto-review-fixes.md)
- [Sprint 6 全维度综合终评](53-v1.2-sprint6-comprehensive-final-review.md)

V1.2 最终代码层放行必须同时满足：最新稳定 head 的 Codex 终审无未解决 P0/P1/P2，以及合并到 `release/v1.2.0` 后 `release-quality`、`release-postgres-migration`、`release-browser-smoke` 三组 CI 全绿。真实服务号、正式数据库/对象存储、恢复、UAT 和灰度仍属于目标环境 Go/No-Go。

## 早期 P0/V1.0.x 评审

以下 24 份记录为早期平台基础和 V1.0.x 的历史评审证据，继续保留用于追溯，但不能单独证明 V1.2 可上线：

| 序号 | 记录 | 历史结论 |
|---:|---|---|
| 1 | [仓库、评审流程与技术对齐基线](00-repository-scaffold.md) | 通过 |
| 2 | [领域模型、数据库、安全与错误契约](01-domain-foundation.md) | 通过 |
| 3 | [内部认证、RBAC、微信邀请绑定与加盟商主数据](02-auth-rbac-company.md) | 通过 |
| 4 | [飞书导入、暂存区、幂等、校验与疑似重复](03-feishu-staging.md) | 通过 |
| 5 | [内部电销核验模板、任务、一键拨号与提交](04-verification.md) | 通过 |
| 6 | [单积分账户、档位、价格、人工充值与不可变流水](05-points.md) | 通过 |
| 7 | [合格客资池、候选资格、人工派发与独占锁](06-dispatch.md) | 通过 |
| 8 | [加盟商领取、扣积分、联系方式解锁与超时回收](07-claim-timeout.md) | 通过 |
| 9 | [加盟商轻量跟进、追加历史与逾期提醒](08-followups.md) | 通过 |
| 10 | [不合格客资证据、私有存储、审核与返积分](09-returns.md) | 通过 |
| 11 | [公众号适配、站内消息、Outbox 重试与安全深链](10-notifications.md) | 通过 |
| 12 | [管理看板、版本配置与审计查询](11-admin-dashboard-config.md) | 通过 |
| 13 | [微信公众号网页授权与安全回跳](12-wechat-oauth.md) | 通过 |
| 14 | [数据库初始化、演示数据与定时任务命令](13-bootstrap-demo-jobs.md) | 通过 |
| 15 | [加盟商微信 H5 业务闭环](14-franchise-h5.md) | 通过 |
| 16 | [内部电销移动核验工作台](15-telesales-h5.md) | 通过 |
| 17 | [Web 管理后台全模块工作台](16-admin-web.md) | 通过 |
| 18 | [容器部署、数据库迁移、调度器与运行手册](17-infrastructure-deployment.md) | 通过 |
| 19 | [HTTP 全链路验收与跨数据库时区修复](18-http-e2e-timezone.md) | 通过 |
| 20 | [定时作业统一与超时提醒幂等修复](19-scheduled-jobs.md) | 通过 |
| 21 | [发布质量报告、PRD 追踪与 OpenAPI 冻结](20-quality-traceability.md) | 通过 |
| 22 | [可复现源码、Git 历史与完整交付包打包](21-release-packaging.md) | 通过 |
| 23 | [P0 代码交付 Gate 与生产边界确认](22-release-gate.md) | 通过 |
| 24 | [源码包无 Git 环境测试兼容修复](23-source-archive-smoke.md) | 通过 |

## 使用规则

1. 每个开发任务应同时提交实现、测试与评审证据；预评审/上下文记录不得伪装成“通过”。
2. 自动评审的 P0/P1/P2 必须有代码或文档处置并关闭线程；有新提交后应重新终审。
3. 发布包必须携带当前版本专属评审索引、综合终评、测试报告、安全审计和上线 Runbook。
4. 生产环境微信、飞书、PostgreSQL、对象存储、恢复演练、UAT 与灰度属于上线 Gate，不以代码自动检查替代。
