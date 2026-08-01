# PRD V1.0 实现追踪矩阵

> 状态“已实现”表示代码基线和自动测试已完成；“待生产联调”表示适配器存在，但必须使用真实企业凭据和目标基础设施验证。

| PRD 域 | P0 能力 | 后端实现 | 前端/入口 | 核心测试 | 状态 |
|---|---|---|---|---|---|
| AUTH | 内部账号、RBAC、微信邀请绑定、OAuth 回调 | `routers/auth.py`、`services/auth_service.py`、`core/auth.py` | 加盟商 H5 登录/邀请页、管理后台登录 | `test_auth_company.py`、`test_wechat_oauth.py`、HTTP 登录 | 已实现；真实微信待联调 |
| ADM | 公司、用户、角色、字段隔离、看板、配置、审计 | `routers/admin.py`、`companies.py`、`users.py`、`services/admin_service.py` | Web 管理后台 | `test_admin_dashboard.py`、HTTP 角色投影 | 已实现 |
| IMP | 飞书同步、暂存、错误、幂等、疑似重复 | `routers/leads.py`、`integrations/feishu.py`、`services/lead_service.py` | 管理后台暂存区 | `test_lead_import.py` | 已实现；真实飞书待联调 |
| VER | 核验模板、任务分配/领取、拨号、提交结果 | `routers/verification.py`、`services/verification_service.py` | 内部电销 H5、后台任务管理 | `test_verification.py` | 已实现 |
| DIS | 合格客资池、候选加盟商、人工派发、独占锁、释放 | `routers/dispatch.py`、`services/dispatch_service.py` | 管理后台人工派发 | `test_dispatch.py`、HTTP 候选投影 | 已实现 |
| CLM | 领取前脱敏、领取扣分、解锁电话、24/48 小时回收 | `routers/claim.py`、`services/claim_service.py` | 加盟商 H5 客资列表/详情 | `test_claim.py`、HTTP 全链路 | 已实现 |
| PNT | 单积分账户、档位、价格规则、线下充值、冲正、流水 | `routers/points.py`、`services/points_service.py` | H5 积分中心、后台人工入账 | `test_points.py`、HTTP 余额对账 | 已实现 |
| FOL | 追加式跟进、首次跟进时限、幂等提醒 | `routers/followups.py`、`services/followup_service.py` | H5 跟进表单 | `test_followups.py`、HTTP 全链路 | 已实现 |
| RET | 退回草稿、截图和录音、提交、补充/驳回/通过、返积分 | `routers/returns.py`、`services/return_service.py`、`services/storage.py` | H5 退回页、后台审核页 | `test_returns.py`、HTTP 全链路 | 已实现；生产存储待联调 |
| NTF | 站内消息、Outbox、重试、微信公众号适配器 | `routers/notifications.py`、`notification_service.py`、`outbox_worker.py` | H5 消息中心、后台 Outbox | `test_notifications.py`、超时提醒幂等测试 | 已实现；真实公众号待联调 |
| NFR/OPS | 加密、哈希、审计、迁移、Docker、Nginx、定时器、备份手册 | `core/security.py`、Alembic、Docker/Compose、runbooks | 三端静态 Web | `test_security.py`、`test_deployment_contract.py`、前端契约测试 | 代码完成；目标环境待演练 |

## 明确不在 P0 范围

- 在线支付、微信支付或支付宝；
- 保证金/钱包双账户；
- 自动轮询派发、抢单、竞价和复杂权重；
- 加盟商老板向内部员工二次派发；
- 云呼叫中心、虚拟号码及 H5 自动录制原生通话；
- 独立 App 和微信小程序前端。

## 追踪规则

- Git 提交信息引用 PRD 域标识，例如 `[DIS][PNT]`；
- 每个任务评审记录位于 `docs/reviews/`；
- 测试失败不得发布；
- 业务规则变更需更新 PRD、配置版本、测试用例与本矩阵。
