# 任务级代码评审索引

> 本索引由 `scripts/generate_review_index.py` 自动生成。`INDEX*.md` 不参与评审记录计数。没有标准评审元数据的历史/上下文文档会保留，但不会误计为“通过”。

- 评审/上下文记录总数：**77**
- 明确通过数：**33**

| 序号 | 评审任务 | 结论 | 评审时间（UTC） | 评审范围 |
|---:|---|---|---|---|
| 1 | [00-repository-scaffold 仓库、评审流程与技术对齐基线](../../docs/reviews/00-repository-scaffold.md) | 通过 | 2026-07-31T16:57:37.290352+00:00 | README、目录、运行规范、评审脚本和源文档 |
| 2 | [01-domain-foundation 领域模型、数据库、安全与错误契约](../../docs/reviews/01-domain-foundation.md) | 通过 | 2026-07-31T17:00:44.660101+00:00 | S0 数据设计/API规范/后端骨架；全局领域实体与约束 |
| 3 | [02-auth-rbac-company 内部认证、RBAC、微信邀请绑定与加盟商主数据](../../docs/reviews/02-auth-rbac-company.md) | 通过 | 2026-07-31T17:02:59.444205+00:00 | AUTH-001~011、ADM-001、公司/地区/类目基础能力 |
| 4 | [03-feishu-staging 飞书导入、暂存区、幂等、校验与疑似重复](../../docs/reviews/03-feishu-staging.md) | 通过 | 2026-07-31T17:04:40.902536+00:00 | IMP-001~012、ADM-04、手机号加密/脱敏 |
| 5 | [04-verification 内部电销核验模板、任务、一键拨号与提交](../../docs/reviews/04-verification.md) | 通过 | 2026-07-31T17:06:08.854938+00:00 | VER-001~011、CALL-01~06、ADM-05 |
| 6 | [05-points 单积分账户、档位、价格、人工充值与不可变流水](../../docs/reviews/05-points.md) | 通过 | 2026-07-31T17:07:33.451983+00:00 | PNT-001~014、ADM-11~13、H5-13~15 |
| 7 | [06-dispatch 合格客资池、候选资格、人工派发与独占锁](../../docs/reviews/06-dispatch.md) | 通过 | 2026-07-31T17:09:00.704555+00:00 | DIS-001~012、ADM-06~08、NTF基础Outbox |
| 8 | [07-claim-timeout 加盟商领取、扣积分、联系方式解锁与24/48小时回收](../../docs/reviews/07-claim-timeout.md) | 通过 | 2026-07-31T17:10:08.430277+00:00 | CLM-001~010、H5-05~08、深链安全 |
| 9 | [08-followups 加盟商轻量跟进、追加历史与逾期提醒](../../docs/reviews/08-followups.md) | 通过 | 2026-07-31T17:10:57.577611+00:00 | FOL-001~006、H5-09 |
| 10 | [0822—Phase01评审记录](../../docs/reviews/0822—Phase01评审记录.md) | 未记录 | - | - |
| 11 | [0822—Phase02评审记录](../../docs/reviews/0822—Phase02评审记录.md) | 未记录 | - | - |
| 12 | [0823—Phase03评审记录](../../docs/reviews/0823—Phase03评审记录.md) | 未记录 | - | - |
| 13 | [0823—上线前终审记录](../../docs/reviews/0823—上线前终审记录.md) | 未记录 | - | - |
| 14 | [09-returns 不合格客资双证据、私有存储、审核与返积分](../../docs/reviews/09-returns.md) | 通过 | 2026-07-31T17:12:49.424888+00:00 | RET-001~014、H5-10~12、ADM-14~15 |
| 15 | [10-notifications 公众号适配、站内消息、Outbox重试与安全深链](../../docs/reviews/10-notifications.md) | 通过 | 2026-07-31T17:13:57.103748+00:00 | NTF-001~009、H5-16/19、通知失败清单 |
| 16 | [11-admin-dashboard-config 管理看板、版本配置与审计查询](../../docs/reviews/11-admin-dashboard-config.md) | 通过 | 2026-07-31T17:17:50.739974+00:00 | Dashboard、SystemConfig、AuditLog API及字段脱敏修复 |
| 17 | [12-wechat-oauth 微信公众号网页授权与安全回跳](../../docs/reviews/12-wechat-oauth.md) | 通过 | 2026-07-31T17:19:24.645319+00:00 | OAuth启动、签名state、回调换取OpenID、公司绑定与Cookie会话 |
| 18 | [13-bootstrap-demo-jobs 数据库初始化、演示数据与定时任务命令](../../docs/reviews/13-bootstrap-demo-jobs.md) | 通过 | 2026-07-31T17:22:05.135946+00:00 | 可重复初始化、演示账号、业务样例、作业CLI和OpenAPI导出 |
| 19 | [14-franchise-h5 加盟商微信H5完整业务闭环](../../docs/reviews/14-franchise-h5.md) | 通过 | 2026-07-31T17:24:55.619857+00:00 | 微信/演示登录、首页、客资领取、跟进、退回双证据、积分、消息与个人中心 |
| 20 | [15-telesales-h5 内部电销移动核验工作台](../../docs/reviews/15-telesales-h5.md) | 通过 | 2026-07-31T17:26:37.299192+00:00 | 任务首页、任务列表、领取锁定、一键拨号、核验表单与权限边界 |
| 21 | [16-admin-web Web管理后台全模块工作台](../../docs/reviews/16-admin-web.md) | 通过 | 2026-07-31T17:30:50.532311+00:00 | 角色菜单、看板、暂存、核验、人工派发、公司、积分、充值、退回、通知、账号、配置与审计 |
| 22 | [17-infrastructure-deployment 容器部署、数据库迁移、调度器与运行手册](../../docs/reviews/17-infrastructure-deployment.md) | 通过 | 2026-07-31T17:34:40.134063+00:00 | Docker Compose、PostgreSQL、Alembic、Nginx、健康检查、Scheduler及运维文档 |
| 23 | [18-http-e2e-timezone HTTP全链路验收与跨数据库时区修复](../../docs/reviews/18-http-e2e-timezone.md) | 通过 | 2026-07-31T17:44:03.512826+00:00 | 隔离数据库HTTP集成测试、前端静态契约、SQLite/PostgreSQL时区一致性 |
| 24 | [19-scheduled-jobs 定时作业统一与超时提醒幂等修复](../../docs/reviews/19-scheduled-jobs.md) | 通过 | 2026-07-31T17:46:23.756473+00:00 | CLI作业、常驻调度器、跟进超时通知去重和回归测试 |
| 25 | [20-quality-traceability 发布质量报告、PRD追踪与OpenAPI冻结](../../docs/reviews/20-quality-traceability.md) | 通过 | 2026-07-31T17:50:25.104500+00:00 | 质量报告、实现矩阵、发布说明、评审索引、接口契约与发布契约测试 |
| 26 | [21-release-packaging 可复现源码、Git历史与完整交付包打包](../../docs/reviews/21-release-packaging.md) | 通过 | 2026-07-31T17:52:29.224220+00:00 | 仅跟踪文件打包、安全排除、Git bundle、SHA256、质量资料和恢复手册 |
| 27 | [22-release-gate P0代码交付Gate与生产边界确认](../../docs/reviews/22-release-gate.md) | 通过 | 2026-07-31T17:55:09.853342+00:00 | 37项测试、68%覆盖、迁移、初始化、定时作业、打包、生产前置条件 |
| 28 | [23-source-archive-smoke 源码包无Git环境测试兼容修复](../../docs/reviews/23-source-archive-smoke.md) | 通过 | 2026-07-31T17:57:31.186800+00:00 | 源码ZIP运行测试时跳过仅适用于Git工作区的打包契约测试 |
| 29 | [24-h5-design-system-v13-home](../../docs/reviews/24-h5-design-system-v13-home.md) | 未记录 | - | - |
| 30 | [25-h5-lead-list-v13](../../docs/reviews/25-h5-lead-list-v13.md) | 未记录 | - | - |
| 31 | [26-h5-lead-detail-v13](../../docs/reviews/26-h5-lead-detail-v13.md) | 未记录 | - | - |
| 32 | [27-h5-points-v13](../../docs/reviews/27-h5-points-v13.md) | 未记录 | - | - |
| 33 | [28-h5-notifications-v13](../../docs/reviews/28-h5-notifications-v13.md) | 未记录 | - | - |
| 34 | [29-h5-profile-v13](../../docs/reviews/29-h5-profile-v13.md) | 未记录 | - | - |
| 35 | [30-h5-followup-v13](../../docs/reviews/30-h5-followup-v13.md) | 未记录 | - | - |
| 36 | [30-h5-remaining-status-pages-v13](../../docs/reviews/30-h5-remaining-status-pages-v13.md) | 未记录 | - | - |
| 37 | [31-admin-foundation-v10](../../docs/reviews/31-admin-foundation-v10.md) | 未记录 | - | - |
| 38 | [31-h5-return-v13](../../docs/reviews/31-h5-return-v13.md) | 未记录 | - | - |
| 39 | [32-admin-lead-operations-v10](../../docs/reviews/32-admin-lead-operations-v10.md) | 未记录 | - | - |
| 40 | [32-h5-v13-integration](../../docs/reviews/32-h5-v13-integration.md) | 未记录 | - | - |
| 41 | [33-admin-company-points-v10](../../docs/reviews/33-admin-company-points-v10.md) | 未记录 | - | - |
| 42 | [34-admin-quality-system-v10](../../docs/reviews/34-admin-quality-system-v10.md) | 未记录 | - | - |
| 43 | [35-admin-capability-gap-closure-v10](../../docs/reviews/35-admin-capability-gap-closure-v10.md) | 未记录 | - | - |
| 44 | [36-h5-admin-joint-acceptance](../../docs/reviews/36-h5-admin-joint-acceptance.md) | 未记录 | - | - |
| 45 | [37-svg-icon-system-v10](../../docs/reviews/37-svg-icon-system-v10.md) | 未记录 | - | - |
| 46 | [38-v1.2-requirements-baseline](../../docs/reviews/38-v1.2-requirements-baseline.md) | 未记录 | - | V1.2 PRD 基线、历史冲突清单、34 项开发计划、需求—任务—测试追踪矩阵 |
| 47 | [39-v1.2-t01-database-foundation](../../docs/reviews/39-v1.2-t01-database-foundation.md) | 未记录 | - | - |
| 48 | [40-v1.2-t02-workday-calendar](../../docs/reviews/40-v1.2-t02-workday-calendar.md) | 未记录 | - | - |
| 49 | [41-v1.2-t03-state-machine](../../docs/reviews/41-v1.2-t03-state-machine.md) | 未记录 | - | - |
| 50 | [42-v1.2-sprint1-lead-supply-backend](../../docs/reviews/42-v1.2-sprint1-lead-supply-backend.md) | 未记录 | - | T04、T06-T10、T12-T13 后端实现 |
| 51 | [43-v1.2-sprint1-lead-supply-ui](../../docs/reviews/43-v1.2-sprint1-lead-supply-ui.md) | 未记录 | - | T05 平台录入后台、T11 供应商 H5、供应商初审队列补充接口 |
| 52 | [44-v1.2-sprint1-ui-review-fixes](../../docs/reviews/44-v1.2-sprint1-ui-review-fixes.md) | 未记录 | - | - |
| 53 | [45-v1.2-sprint2-dispatch-claim-backend](../../docs/reviews/45-v1.2-sprint2-dispatch-claim-backend.md) | 未记录 | - | - |
| 54 | [46-v1.2-sprint3-return-verification-backend](../../docs/reviews/46-v1.2-sprint3-return-verification-backend.md) | 未记录 | - | - |
| 55 | [47-v1.2-sprint4-supplier-rewards](../../docs/reviews/47-v1.2-sprint4-supplier-rewards.md) | 未记录 | - | - |
| 56 | [48-v1.2-sprint4-auto-review-fixes](../../docs/reviews/48-v1.2-sprint4-auto-review-fixes.md) | 未记录 | - | - |
| 57 | [V1.2 Sprint 5 H5、后台、通知与洞察集成](../../docs/reviews/49-v1.2-sprint5-integration.md) | 通过 | 2026-08-06T17:20:00Z | T26–T29 加盟商 H5、平台运营后台、事务通知/深链、V1.2 报表审计与业务追踪 |
| 58 | [50-v1.2-sprint6-pre-review](../../docs/reviews/50-v1.2-sprint6-pre-review.md) | 未记录 | - | - |
| 59 | [V1.2 Sprint 6 自动评审问题整改](../../docs/reviews/51-v1.2-sprint6-auto-review-fixes.md) | 全部已知 P1/P2 已整改并关闭线程，等待当前最新 head 最终复审与 Release CI | 2026-08-07T07:10:00+08:00 | Sprint 6 PR #35/#37 自动评审提出的迁移、账务、S3、飞书、Compose Preflight、数据库凭据、镜像版本、历史账务兼容与证据持久化问题 |
| 60 | [52-v1.2-sprint6-final-validation-context](../../docs/reviews/52-v1.2-sprint6-final-validation-context.md) | 未记录 | - | - |
| 61 | [V1.2 Sprint 6 全维度综合终评](../../docs/reviews/53-v1.2-sprint6-comprehensive-final-review.md) | 条件通过——全部已知 P1/P2 已整改并关闭；等待当前稳定 head Codex 终审与合并后 Release 三组 CI | 2026-08-07T07:20:00+08:00 | V1.2 Sprint 0–6 最终合并差异，重点覆盖 T30–T33 的历史迁移、全量质量安全、浏览器验收、生产部署、UAT/灰度/回滚与可构建发布交付 |
| 62 | [54-main-release-ci-v12](../../docs/reviews/54-main-release-ci-v12.md) | 未记录 | - | - |
| 63 | [55-v1.2-h01-legacy-isolation](../../docs/reviews/55-v1.2-h01-legacy-isolation.md) | 未记录 | - | - |
| 64 | [56-v1.2-h02-demo-credentials](../../docs/reviews/56-v1.2-h02-demo-credentials.md) | 未记录 | - | - |
| 65 | [57-v1.2-h03-auth-hardening](../../docs/reviews/57-v1.2-h03-auth-hardening.md) | 未记录 | - | - |
| 66 | [58-v1.2-h05-security-negative-tests](../../docs/reviews/58-v1.2-h05-security-negative-tests.md) | 未记录 | - | - |
| 67 | [59-v1.2-h06-coverage-gate](../../docs/reviews/59-v1.2-h06-coverage-gate.md) | 未记录 | - | - |
| 68 | [60-v1.2-h07-security-analysis](../../docs/reviews/60-v1.2-h07-security-analysis.md) | 未记录 | - | - |
| 69 | [61-v1.2-p1-infrastructure](../../docs/reviews/61-v1.2-p1-infrastructure.md) | 未记录 | - | - |
| 70 | [FEISHU-001 飞书真实同步与状态回写](../../docs/reviews/FEISHU-001.md) | 通过 | - | - |
| 71 | [H5-001 加盟商微信 H5 生产体验增强](../../docs/reviews/H5-001.md) | 通过 | - | - |
| 72 | [OPS-ENH-001 生产部署、安全日志、健康检查与备份恢复增强](../../docs/reviews/OPS-ENH-001.md) | 通过 | 2026-08-01T12:45:40+00:00 | 生产环境校验、结构化日志、TLS/Nginx、容器最小权限、健康检查、备份恢复和发布文档 |
| 73 | [PNT-ENH-001 积分档位、等级权益、预警、充值确认与对账增强](../../docs/reviews/PNT-ENH-001.md) | 通过 | 2026-08-01T12:19:26+00:00 | 积分档位、价格规则、充值入账、低积分提醒、会员权益、积分对账及前端增强 |
| 74 | [REL-V101-001 V1.0.1 CI、发布资料与完整代码包](../../docs/reviews/REL-V101-001.md) | 通过 | 2026-08-01T13:13:00+00:00 | V1.0.1 发布说明、评审索引、CI、源码 ZIP、Git Bundle、完整交付包和 SHA-256 |
| 75 | [RPT-ENH-001 角色化经营漏斗、区域与积分报表增强](../../docs/reviews/RPT-ENH-001.md) | 通过 | 2026-08-01T12:31:38+00:00 | 经营漏斗、区域表现、积分报表与管理后台增强 |
| 76 | [WECHAT-001 生产微信OAuth登录与重复登录](../../docs/reviews/WECHAT-001.md) | 通过 | 2026-08-01T10:55:09.267273+00:00 | 当前提交变更 |
| 77 | [WECHAT-002 客资消息深链接安全加固](../../docs/reviews/WECHAT-002.md) | 通过 | - | 签名令牌、公司隔离、订单实时状态校验、审计记录 |

## 使用规则

1. 每个开发任务应提交实现、测试与对应评审记录；上下文/预评审文档不得伪装成已通过结论。
2. 评审失败时不得进入发布分支；修复后重新执行对应评审。
3. 生产环境微信、飞书、PostgreSQL、对象存储、恢复演练、UAT 与灰度属于上线 Gate，不以代码级自动检查替代。
