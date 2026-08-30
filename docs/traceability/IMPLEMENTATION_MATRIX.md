# 合家美宅客资平台 V1.2 实现追踪矩阵

> 状态必须分层记录：`代码存在`只说明实现与入口可定位；`自动化通过`只说明当前分支的自动门禁已有通过证据；`待真实环境验收`表示仍须在目标 PostgreSQL、对象存储、微信 WebView 或真实业务角色中执行。API 测试不能代替缺失的 UI，也不能代替生产验收。

| 领域 | V1.2 能力 | 后端/脚本 | 前端/入口 | 自动化验证 | 真实环境验收 |
|---|---|---|---|---|---|
| AUTH | 内部账号、RBAC、微信 OAuth、公司绑定、安全深链 | `apps/api/src/routers/auth.py`、`apps/api/src/services/auth_service.py` | `apps/admin/public/v12-operations.html`、`apps/admin/public/h5/index.html`、`apps/h5/public/v12-workbench.html` | `apps/api/tests/test_v12_auth_hardening.py`：自动化通过 | 待真实服务号 OAuth、公司绑定和全角色 UAT |
| SUP | 平台手工供给、加盟商草稿/提交、资料初审 | `apps/api/src/routers/v12_lead_supply.py`、`apps/api/src/services/lead_supply_v12.py` | `apps/admin/public/v12-operations.html`、`apps/h5/public/v12-workbench.html` | `apps/api/tests/test_v12_lead_supply.py`、`apps/api/tests/test_v12_lead_supply_ui_contract.py`：自动化通过 | 待真实业务角色和生产数据 UAT |
| DEDUP | 独立手机号指纹、90/180/365 天窗口、历史关系、覆盖审计、自供自领阻止 | `apps/api/src/services/dedup_v12.py`、`apps/api/src/core/security.py`、`apps/api/src/services/dispatch_v12.py` | `apps/admin/public/v12-operations.html` | `apps/api/tests/test_v12_lead_supply.py`、`apps/api/tests/test_v12_sprint6_migration.py`、`apps/api/tests/test_v12_dispatch_claim.py`：自动化通过 | 待生产密钥托管和生产数据抽样；配置与微信密钥相关 Gate 当前暂缓 |
| CAP/REGION | 供给/接收能力、主要城市、服务区申请与审核；同一开通申请一键通过 | `apps/api/src/services/company_profile_v12.py`、`apps/api/src/routers/v12_lead_supply.py` | `apps/h5/public/v12-workbench.html`、`apps/admin/public/v12-operations.html` | `apps/api/tests/test_v12_company_profile_http.py`、`apps/api/tests/test_v12_company_profile_ui_contract.py`：自动化通过 | 待真实公司初始化、区域审核和全角色 UAT |
| DISPATCH | 待派发池、候选过滤、人工派发、积分预留；退回后默认排除原领取公司，例外原因审计 | `apps/api/src/services/dispatch_v12.py`、`apps/api/src/routers/v12_dispatch.py` | `apps/admin/public/v12-operations.html` | `apps/api/tests/test_v12_dispatch_claim.py`、`apps/api/tests/test_v12_dispatch_http.py`：自动化通过 | 待真实运营角色、生产数据和 PostgreSQL UAT |
| CLAIM | 原子领取、扣分、手机号解锁、3 工作日截止、奖励快照 | `apps/api/src/services/dispatch_v12.py`、`apps/api/src/routers/v12_dispatch.py` | `apps/h5/public/v12-workbench.html` | `apps/api/tests/test_v12_dispatch_claim.py`、`apps/api/tests/test_v12_production_lifecycle_e2e.py`：自动化通过 | 待真实加盟商、生产账务与移动端 UAT |
| COLLAB | 负责人内部交接/回收、员工任务隔离、运营公司级汇总、超级管理员理由审计 | `apps/api/src/services/company_assignment_v12.py`、`apps/api/src/routers/v12_dispatch.py` | `apps/h5/public/v12-workbench.html`、`apps/admin/public/v12-operations.html` | `apps/api/tests/test_company_assignment_collaboration.py`、`apps/api/tests/test_v12_company_profile_ui_contract.py`：自动化通过 | 待真实负责人/员工移动端交接和审计抽样 UAT |
| RETURN | 四类申诉、截图或录音、逾期、补证保留原证据并通知申请人 | `apps/api/src/services/return_v12.py`、`apps/api/src/routers/v12_returns.py` | `apps/h5/public/v12-workbench.html` | `apps/api/tests/test_v12_return_workflow.py`、`apps/api/tests/test_formal_workbench_static_contract.py`：自动化通过 | 待真实对象存储、微信 WebView 和业务 UAT |
| VERIFY | 仅申诉后创建核验任务、电销事实结论与通话依据、运营终审分权 | `apps/api/src/services/return_v12.py`、`apps/api/src/routers/v12_returns.py` | `apps/call-h5/public/index.html`、`apps/admin/public/v12-operations.html` | `apps/api/tests/test_call_h5_v12_contract.py`、`apps/api/tests/test_v12_return_workflow.py`：自动化通过 | 待真实电销与退回终审角色 UAT |
| REFUND | 终审通过一次返分、回池、奖励取消；驳回恢复 | `apps/api/src/services/return_v12.py` | `apps/admin/public/v12-operations.html` | `apps/api/tests/test_v12_return_workflow.py`、`apps/api/tests/test_v12_reconciliation_legacy.py`：自动化通过 | 待生产账务抽样与财务/运营联合 UAT |
| REWARD | 规则快照、观察/冻结/结算、异常冲正 | `apps/api/src/services/supplier_reward_v12.py`、`apps/api/src/routers/v12_rewards.py` | `apps/h5/public/v12-workbench.html`、`apps/admin/public/v12-operations.html` | `apps/api/tests/test_v12_supplier_rewards.py`、`apps/api/tests/test_v12_reward_scheduler_contract.py`：自动化通过 | 待批准规则、生产账务和财务 UAT；参数配置当前暂缓 |
| FUNDS | 超级管理员统一资金页：充值、调账、档位、价格、奖励结算/冲正、单公司对账；运营与电销不得写资金 | `apps/api/src/routers/points.py`、`apps/api/src/routers/v12_rewards.py`、`apps/api/src/services/points_service.py` | `apps/admin/public/v12-operations.html`、`apps/admin/public/h5/index.html` | `apps/api/tests/test_points_enhancement.py`、`apps/api/tests/test_v12_production_lifecycle_e2e.py`、`apps/api/tests/test_h5_admin_workbench_contract.py`：自动化通过 | 待真实收款凭证、生产账务抽样、灰度对账和财务 UAT |
| NTF | 状态变化通知、退回补证/终审与公司资料审核通知、站内消息、Outbox、业务深链 | `apps/api/src/services/notification_v12.py`、`apps/api/src/services/outbox_worker.py` | `apps/h5/public/v12-workbench.html`、`apps/admin/public/v12-operations.html` | `apps/api/tests/test_v12_sprint5_notifications.py`：自动化通过 | 待真实微信发送、失败重试和深链 UAT；需配置退回与公司资料审核事件模板 |
| REPORT/AUDIT | 平台/本公司报表、审计事件、业务 ID 全链路追踪 | `apps/api/src/routers/v12_insights.py`、`apps/api/src/services/audit.py` | `apps/h5/public/v12-workbench.html`、`apps/admin/public/v12-operations.html` | `apps/api/tests/test_v12_sprint5_insights.py`、`apps/api/tests/test_v12_audit_security.py`：自动化通过 | 待真实角色、生产数据口径和审计抽样 UAT |
| MIGRATION | 历史手机号指纹回填、严格状态映射、数据对账 | `apps/api/src/services/migration_v12.py`、`apps/api/src/services/reconciliation_v12.py`、`scripts/migrate_v12_data.py`、`scripts/reconcile_v12.py` | 无用户界面；仅受控运维入口 | `apps/api/tests/test_v12_sprint6_migration.py`、`apps/api/tests/test_v12_postgres_constraint_gate.py`：自动化通过 | 待生产备份副本预演、正式执行和签字 |
| BROWSER | Chromium 桌面运营台和移动视口 H5 渲染/交互门禁 | `scripts/browser_smoke_v12.py` | `apps/admin/public/v12-operations.html`、`apps/admin/public/h5/index.html`、`apps/h5/public/v12-workbench.html`、`apps/call-h5/public/index.html` | `apps/api/tests/test_v12_browser_smoke_contract.py`、`apps/api/tests/test_h5_admin_workbench_contract.py`：自动化通过 | 待 iOS/Android 微信 WebView、目标桌面浏览器和人工视觉 UAT |
| SECURITY | 密钥隔离、敏感字段脱敏、私有文件、依赖审计 | `apps/api/src/core/production.py`、`scripts/secret_scan.py` | 全端后端强制，不依赖前端隐藏 | `apps/api/tests/test_pre_go_live_security_review.py`、`apps/api/tests/test_v12_audit_security.py`：自动化通过 | 待目标环境安全基线、渗透与密钥托管验收；微信密钥事项当前暂缓 |
| OPS | 显式迁移、生产预检、备份恢复、回滚、灰度 | `scripts/preflight_v12.py`、`scripts/verify_production.py`、`scripts/bootstrap_superadmin.py` | 运维命令与 Runbook | `apps/api/tests/test_v12_release_readiness_contract.py`、`apps/api/tests/test_production_scripts_contract.py`：自动化通过 | 待真实恢复演练、灰度和 Go/No-Go 签字 |
| FEEDBACK-829 | 客资反馈 1–10：1–9 的看板、流转、更正、筛选、导出与当前运营已处理；第 10 条运营/管理共享公海池、后台录入、逐行新增、飞书客户视图手动单向导入、幂等与转池复核；客户来源区分运营录入/加盟商提供，加盟商客资无本地接收方时暂存并可重新匹配 | `apps/api/src/routers/v12_insights.py`、`apps/api/src/routers/v12_lead_supply.py`、`apps/api/src/routers/v12_public_pool.py`、`apps/api/src/services/lead_supply_v12.py`、`apps/api/src/services/public_pool_v12.py`、`apps/api/src/services/dispatch_v12.py`、`apps/api/src/services/lead_export_v12.py`、`scripts/lead_export_worker.py` | `apps/admin/public/v12-operations.html`、`apps/admin/public/v12-operations.js`、`apps/h5/public/v12-workbench.js` | `apps/api/tests/test_customer_feedback_829.py`、`apps/api/tests/test_customer_feedback_829_completion_item5.py`、`apps/api/tests/test_customer_feedback_829_completion_item8.py`、`apps/api/tests/test_customer_feedback_829_completion_ui.py`、`apps/api/tests/test_public_pool_v12.py`、`apps/api/tests/test_public_pool_ui_contract.py`、`apps/api/tests/test_v12_state_machine.py`、`apps/api/tests/test_feishu_client.py`、`apps/api/tests/test_quick_dispatch_postgres_concurrency_e2e.py` | 待生产飞书只读凭据与“客户视图”实表联调、无覆盖加盟商客资重新匹配、完整手机号批量导出容量验证和全角色 UAT |

## Sprint 6 T30–T33 证据

| 任务 | 代码/文档证据 | 自动化门禁 | 现场证据 |
|---|---|---|---|
| T30 | `apps/api/src/services/migration_v12.py`、`scripts/migrate_v12_data.py`、`scripts/reconcile_v12.py`、`docs/runbooks/V1.2_MIGRATION_RUNBOOK.md` | PostgreSQL 历史夹具、错误脱敏、幂等与对账测试 | 生产副本预演、迁移日志、财务抽样 |
| T31 | `scripts/performance_v12.py`、`docs/runbooks/V1.2_PERFORMANCE_CAPACITY.md` | PR/Release 门禁验证压测合同可运行且禁止 PR 访问 staging | staging 合成租户并发报告、目标资源指标、签字门禁与故障注入 |
| T32 | `scripts/browser_smoke_v12.py`、`docs/runbooks/V1.2_UAT.md` | 桌面与移动视口 Chromium | iOS/Android 微信、Chrome/Edge、人工视觉对照、业务签字 |
| T33 | `scripts/preflight_v12.py`、`docs/runbooks/DEPLOYMENT.md`、`docs/runbooks/V1.2_ROLLBACK.md`、`docs/runbooks/V1.2_POST_LAUNCH.md` | 配置合同、Alembic 与对账门禁 | 真实服务号、备份恢复、3–5 家灰度、Go/No-Go 签字 |

## 明确不在 V1.2 范围

- 在线支付、微信支付或支付宝；
- 自动、随机、轮询、权重、竞价或抢单派发；
- 向其他公司或平台公开加盟商内部员工分配明细；
- 微信小程序或独立 App；
- 云呼叫中心、虚拟号码或 H5 自动录制原生通话。

## 追踪规则

- 业务规则变更必须同步 PRD、迁移、配置、测试和本矩阵；
- 高风险变更必须有 `docs/reviews/` 记录；
- PR 和 Release 门禁失败不得合并或发布；
- 真实生产门禁未签字时，即使代码和自动化完成也保持 `NO-GO`。
