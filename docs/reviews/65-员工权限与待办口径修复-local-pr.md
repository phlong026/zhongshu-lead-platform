# 本地 PR 与代码评审：员工权限边界与待办口径修复

- 评审日期：2026-08-29
- 目标分支：`main`（基准 `2b868db`）
- 来源分支：`fix/employee-access-and-todo-scope`
- 本地 PR 差异：`main...fix/employee-access-and-todo-scope`
- 提交结构：P1-1 独立提交；P2-2/P2-3/P2-4/P3-6/P2-5 合并为第二个逻辑提交
- 总体结论：独立代码评审 `APPROVE`，可以合并到本地 `main`

## 一、实际执行顺序

本轮严格先补失败回归测试，再按下列顺序修复：

1. P1-1：旧详情接口的跨公司与员工内部归属越权。
2. P2-2：平台经营汇总与预警的角色边界。
3. P2-3：退回原提交人的持续访问、补证和重提权限。
4. P2-4：站内消息按负责人和相关员工拆分，已读状态互不影响。
5. P3-6：候选公司服务端搜索、分页和分页前完整资格排序。
6. P2-5：前置电销核验与退回核验分别统计、分别跳转。

P3-6 已按用户补充要求放在 P2-5 之前完成；全部实现与评审修正完成后，才执行最终全量 `pytest`。

## 二、修改前后对比

| 问题 | 修改前 | 修改后 |
|---|---|---|
| P1-1 旧详情读取 | 员工可绕过旧 GET 接口读取跨公司或同公司非本人数据；电销可凭 ID 读取未分配客资 | 客资、派发单、领取详情均显式校验公司与员工归属；电销无 `lead.read` 时返回 403 |
| 联系方式解锁 | 加盟商在领取前可能从旧客资详情看到明文手机号 | 只有派发单进入已领取联系方式状态后才返回明文手机号，领取前仅返回掩码号 |
| P2-2 全局看板 | 员工可通过 `h5.home` 读取平台经营汇总，员工与电销可读平台预警 | 汇总与预警只允许运营看板权限或全局权限角色访问 |
| P2-3 退回记录 | 原提交员工被内部转派后，报表仍有计数，但列表、详情、补证和重提均不可用 | 原提交人在同公司范围内始终可查看、补证和重提；当前归属员工仍保留既有权限 |
| P2-4 站内消息 | 公司级消息同公司全员可见，共享同一 `read_at` | 新业务消息分别投递给负责人及业务相关员工，每位收件人拥有独立消息和已读状态；历史公司消息仅负责人可见 |
| P3-6 候选公司 | 接口一次读取和返回全部公司，浏览器端筛选 | 默认每页 20 条，支持服务端关键词搜索和加载更多；在 SQL 分页前完成区域、资格、名称与 ID 的稳定排序 |
| P2-5 待办口径 | 运营首页的电销待办混入退回核验，点击后数字与列表不一致 | `PRE_DISPATCH_VERIFY` 与 `RETURN_VERIFY` 独立统计，分别跳转电销页和退回页 |

保持不变的安全合同：`GET /dispatch/assignments` 列表对加盟商员工仍返回 403；已流转业务数据没有新增物理删除能力。

## 三、独立评审发现并闭环的问题

首轮独立评审提出 2 个 HIGH、3 个 MEDIUM，均补失败回归测试后修正：

- 候选资格必须在数据库分页前计算与排序，避免真正可派发公司被截断到后页。
- 旧客资详情同时封堵电销 IDOR，并把手机号解锁绑定到领取状态。
- 退回证据上传必须先校验归属，再读取文件或写对象存储。
- 原提交员工的重提用例改为真实调用提交接口，并验证新一轮退回核验任务。
- 候选名称统一使用 SQL 的 `lower(name), name, id` 稳定顺序，避免页内 Python 二次排序造成跨页顺序漂移。

最终复审结论：`APPROVE`，无剩余阻断项或 MEDIUM 问题。当前环境没有 LSP diagnostics 工具，此限制由 Python 编译、JavaScript 语法检查和全量测试补充覆盖。

## 四、变更文件

### 权限与业务实现

- `apps/api/src/routers/admin.py`
- `apps/api/src/routers/dispatch.py`
- `apps/api/src/routers/leads.py`
- `apps/api/src/routers/notifications.py`
- `apps/api/src/routers/v12_dispatch.py`
- `apps/api/src/routers/v12_insights.py`
- `apps/api/src/routers/v12_returns.py`
- `apps/api/src/services/claim_service.py`
- `apps/api/src/services/company_assignment_v12.py`
- `apps/api/src/services/dispatch_v12.py`
- `apps/api/src/services/lead_service.py`
- `apps/api/src/services/notification_v12.py`
- `apps/api/src/services/return_v12.py`
- `apps/admin/public/v12-operations.js`

### 回归测试与审查证据

- `apps/api/tests/test_employee_legacy_read_scope.py`
- `apps/api/tests/test_employee_scope_and_todo_regressions.py`
- `apps/api/tests/test_v12_sprint5_insights.py`
- `docs/reviews/64-员工越权与待办口径排查-校准报告-2026-08-29.md`
- `docs/reviews/65-员工权限与待办口径修复-local-pr.md`

## 五、验证证据

- 最终全量测试：`838 passed, 10 skipped, 16 warnings`，耗时 102.33 秒。
- 独立复审候选相关测试：30 项通过。
- Python：`compileall` 通过。
- JavaScript：`node --check apps/admin/public/v12-operations.js` 通过。
- 差异格式：`git diff --check main...HEAD` 通过。
- 依赖一致性：48 个 Python 包全部兼容。
- 敏感信息扫描：仅命中测试登录参数和固定测试密码，未发现真实密钥、令牌或私钥特征。
- 回滚检查：反向补丁可干净应用；无数据库迁移、无新增依赖。

## 六、性能与安全复核

- 候选公司仍为单条有界分页查询，没有逐公司 N+1；重复领取、退回原公司、区域和积分资格均进入分页前排序条件。
- 候选搜索按公司名称或编码过滤，`page_size` 最大 100，关键词最大 128 字符。
- 权限判断复用现有公司派发归属函数，只增加退回原提交人的窄范围例外。
- 通知外部投递仍保持每个业务事件一条 outbox；仅站内消息按收件人展开，避免重复触发微信公众号消息。

## 七、本地合并以外的门禁

- 本轮只做本地 PR 与本地合并，不推送远程、不部署生产。
- 未执行真实微信公众号投递、真实账号手机端和浏览器人工验收。
- 公众号真实名称与菜单路径仍按既定决定保持暂定，待取得真实配置后单独修改和验收。
