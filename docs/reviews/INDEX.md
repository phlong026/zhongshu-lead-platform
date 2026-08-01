# 任务级代码评审索引

> 本索引由 `scripts/generate_review_index.py` 自动生成。每一项任务在提交前均执行 Python 编译、后端测试、前端 JavaScript 语法检查与敏感信息扫描。

- 评审记录总数：**24**
- 通过数：**24**

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
| 10 | [09-returns 不合格客资双证据、私有存储、审核与返积分](../../docs/reviews/09-returns.md) | 通过 | 2026-07-31T17:12:49.424888+00:00 | RET-001~014、H5-10~12、ADM-14~15 |
| 11 | [10-notifications 公众号适配、站内消息、Outbox重试与安全深链](../../docs/reviews/10-notifications.md) | 通过 | 2026-07-31T17:13:57.103748+00:00 | NTF-001~009、H5-16/19、通知失败清单 |
| 12 | [11-admin-dashboard-config 管理看板、版本配置与审计查询](../../docs/reviews/11-admin-dashboard-config.md) | 通过 | 2026-07-31T17:17:50.739974+00:00 | Dashboard、SystemConfig、AuditLog API及字段脱敏修复 |
| 13 | [12-wechat-oauth 微信公众号网页授权与安全回跳](../../docs/reviews/12-wechat-oauth.md) | 通过 | 2026-07-31T17:19:24.645319+00:00 | OAuth启动、签名state、回调换取OpenID、公司绑定与Cookie会话 |
| 14 | [13-bootstrap-demo-jobs 数据库初始化、演示数据与定时任务命令](../../docs/reviews/13-bootstrap-demo-jobs.md) | 通过 | 2026-07-31T17:22:05.135946+00:00 | 可重复初始化、演示账号、业务样例、作业CLI和OpenAPI导出 |
| 15 | [14-franchise-h5 加盟商微信H5完整业务闭环](../../docs/reviews/14-franchise-h5.md) | 通过 | 2026-07-31T17:24:55.619857+00:00 | 微信/演示登录、首页、客资领取、跟进、退回双证据、积分、消息与个人中心 |
| 16 | [15-telesales-h5 内部电销移动核验工作台](../../docs/reviews/15-telesales-h5.md) | 通过 | 2026-07-31T17:26:37.299192+00:00 | 任务首页、任务列表、领取锁定、一键拨号、核验表单与权限边界 |
| 17 | [16-admin-web Web管理后台全模块工作台](../../docs/reviews/16-admin-web.md) | 通过 | 2026-07-31T17:30:50.532311+00:00 | 角色菜单、看板、暂存、核验、人工派发、公司、积分、充值、退回、通知、账号、配置与审计 |
| 18 | [17-infrastructure-deployment 容器部署、数据库迁移、调度器与运行手册](../../docs/reviews/17-infrastructure-deployment.md) | 通过 | 2026-07-31T17:34:40.134063+00:00 | Docker Compose、PostgreSQL、Alembic、Nginx、健康检查、Scheduler及运维文档 |
| 19 | [18-http-e2e-timezone HTTP全链路验收与跨数据库时区修复](../../docs/reviews/18-http-e2e-timezone.md) | 通过 | 2026-07-31T17:44:03.512826+00:00 | 隔离数据库HTTP集成测试、前端静态契约、SQLite/PostgreSQL时区一致性 |
| 20 | [19-scheduled-jobs 定时作业统一与超时提醒幂等修复](../../docs/reviews/19-scheduled-jobs.md) | 通过 | 2026-07-31T17:46:23.756473+00:00 | CLI作业、常驻调度器、跟进超时通知去重和回归测试 |
| 21 | [20-quality-traceability 发布质量报告、PRD追踪与OpenAPI冻结](../../docs/reviews/20-quality-traceability.md) | 通过 | 2026-07-31T17:50:25.104500+00:00 | 质量报告、实现矩阵、发布说明、评审索引、接口契约与发布契约测试 |
| 22 | [21-release-packaging 可复现源码、Git历史与完整交付包打包](../../docs/reviews/21-release-packaging.md) | 通过 | 2026-07-31T17:52:29.224220+00:00 | 仅跟踪文件打包、安全排除、Git bundle、SHA256、质量资料和恢复手册 |
| 23 | [22-release-gate P0代码交付Gate与生产边界确认](../../docs/reviews/22-release-gate.md) | 通过 | 2026-07-31T17:55:09.853342+00:00 | 37项测试、68%覆盖、迁移、初始化、定时作业、打包、生产前置条件 |
| 24 | [23-source-archive-smoke 源码包无Git环境测试兼容修复](../../docs/reviews/23-source-archive-smoke.md) | 通过 | 2026-07-31T17:57:31.186800+00:00 | 源码ZIP运行测试时跳过仅适用于Git工作区的打包契约测试 |

## 使用规则

1. 每个小任务必须同时提交实现、测试与对应评审记录。
2. 评审失败时不得进入主分支；修复后重新执行同一任务评审。
3. 生产环境微信、飞书、PostgreSQL 和对象存储联调属于上线 Gate，不以本地自动检查替代。
