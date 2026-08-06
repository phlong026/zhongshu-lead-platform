# V1.2 实现追踪矩阵

> “代码完成”表示实现、自动测试和评审门禁已纳入仓库；“待现场验收”表示必须在真实服务号、目标基础设施或真实业务角色中执行，不能由模拟环境替代。

| 领域 | V1.2 能力 | 后端/脚本 | 前端/入口 | 自动验证 | 交付状态 |
|---|---|---|---|---|---|
| AUTH | 内部账号、RBAC、微信 OAuth、公司绑定、安全深链 | `routers/auth.py`、`services/auth_service.py` | H5 登录/邀请/状态页 | OAuth、公司隔离、无权深链测试 | 代码完成；真实微信待现场验收 |
| SUP | 平台手工供给、供应商草稿/提交、资料初审 | `routers/v12_leads.py`、`services/lead_supply_v12.py` | `admin/v12-leads.html`、`h5/supplier.html` | V1.2 供给 API、归属、初审和前端契约 | 代码完成 |
| DEDUP | 独立手机号指纹、90/180/365、历史关系、覆盖审计 | `services/dedup_v12.py`、`core/security.py` | 初审和详情去重结论 | 动态窗口、覆盖权限、历史迁移 | 代码完成；生产密钥和数据抽样待现场验收 |
| CAP/REGION | 供给/接收能力、主要城市、服务区审核 | `services/company_profile_v12.py` | H5 能力申请、后台审核 | 能力状态、层级和区域生效测试 | 代码完成；正式公司配置待初始化 |
| DISPATCH | 待派发池、候选过滤、人工派发、积分预留 | `services/dispatch_v12.py`、`routers/v12_dispatch.py` | `admin/v12-operations.html` | 自供自领、重复、区域、积分、幂等、数据库唯一约束 | 代码完成；PostgreSQL并发门禁已加入 |
| CLAIM | 原子领取、扣分、手机号解锁、3工作日截止、奖励快照 | `services/claim_v12.py` | `h5/v12-workbench.html` | 扣分幂等、截止固化、字段隔离、奖励观察 | 代码完成 |
| RETURN | 四类申诉、截图或录音、逾期、补证 | `services/return_v12.py`、`routers/v12_returns.py` | V1.2 H5退回流程 | 单证据、原因、截止、重复提交测试 | 代码完成；真实对象存储待现场验收 |
| VERIFY | 仅申诉后创建核验任务、电销事实结论、终审分权 | `services/return_verification_v12.py` | 电销H5、V1.2运营台 | 分配、领取、手机号权限、终审前置条件 | 代码完成 |
| REFUND | 终审通过一次返分、回池、奖励取消；驳回恢复 | `services/return_verification_v12.py` | V1.2运营台 | 返分幂等、状态恢复、多轮补证 | 代码完成 |
| REWARD | 规则快照、观察/冻结/结算、异常冲正、版本配置 | `services/supplier_reward_v12.py`、`routers/v12_rewards.py` | H5奖励、后台奖励管理 | 公式、上下限、幂等、积压排空、冲正负余额 | 代码完成 |
| NTF | 状态变化通知、站内消息、Outbox、业务深链 | `services/notification_v12.py`、`outbox_worker.py` | H5消息、后台深链 | 事件键幂等、审计投影、Scheduler包装器 | 代码完成；真实微信发送待现场验收 |
| REPORT/AUDIT | 平台/本公司报表、审计事件、业务ID全链路追踪 | `routers/v12_insights.py` | V1.2 H5/运营台 | RBAC、未知ID、递归脱敏 | 代码完成 |
| MIGRATION | 历史手机号指纹回填、严格状态映射、数据对账 | `services/migration_v12.py`、`reconciliation_v12.py`、CLI | 无 | SQLite单测、PostgreSQL16历史夹具升级 | 代码完成；生产备份副本和正式执行待现场门禁 |
| BROWSER | 桌面运营台和移动H5真实渲染/交互 | `scripts/browser_smoke_v12.py` | 1440×900后台、390×844 H5 | Chromium登录、加载、console/pageerror、截图 | 自动门禁完成；iOS/Android微信和Figma人工对照待UAT |
| SECURITY | 密钥隔离、敏感字段脱敏、私有文件、依赖审计 | `core/production.py`、`secret_scan.py`、pip-audit | 全端 | 权限负测、密钥扫描、依赖审计、上传契约 | 代码门禁完成；渗透和目标环境配置待验收 |
| OPS | 显式迁移、生产预检、备份恢复、回滚、灰度 | `preflight_v12.py`、Docker/Compose、Runbooks | 运维入口 | 配置契约、迁移门禁、发布文档检查 | 工具和文档完成；真实恢复、灰度和全量批准待现场执行 |

## Sprint 6 T30–T33 证据

| 任务 | 代码/文档证据 | 自动门禁 | 现场证据 |
|---|---|---|---|
| T30 | `migration_v12.py`、`migrate_v12_data.py`、`reconcile_v12.py`、迁移Runbook | PostgreSQL历史夹具、错误脱敏、幂等与对账测试 | 生产副本预演、迁移日志、财务抽样 |
| T31 | 全量测试、生产配置测试、依赖审计、PostgreSQL CI | PR/Release三组任务 | 容量压测、目标环境故障注入、安全验收 |
| T32 | Playwright脚本、截图Artifact、UAT文档 | 桌面与移动Chromium | iOS/Android微信、Chrome/Edge、Figma对照、业务签字 |
| T33 | preflight、显式迁移、部署/回滚/灰度/复盘文档 | 配置、Alembic、对账门禁 | 真实服务号、备份恢复、3–5家灰度、Go/No-Go签字 |

## 明确不在 V1.2 范围

- 在线支付、微信支付或支付宝；
- 自动、随机、轮询、权重、竞价或抢单派发；
- 加盟商老板向内部员工二次派发；
- 微信小程序或独立App；
- 云呼叫中心、虚拟号码或H5自动录制原生通话。

## 追踪规则

- 业务规则变更必须同步PRD、迁移、配置、测试和本矩阵；
- 高风险变更必须有 `docs/reviews/` 记录；
- PR和Release门禁失败不得合并或发布；
- 真实生产门禁未签字时，即使代码完成也保持 `NO-GO`。
