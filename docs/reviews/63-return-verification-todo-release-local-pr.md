# 本地 PR 与代码评审：退回核验待办释放修复

- 评审日期：2026-08-29
- 目标分支：`main`（基准 `0b94de0`）
- 来源分支：`fix/return-verification-todo-release`
- 代码提交：`fbdf01b`
- 本地 PR 差异：`main...fix/return-verification-todo-release`
- 总体结论：代码评审 `APPROVE`，架构审查 `CLEAR`，可以合并到本地 `main`
- 明确延后：修复清单第 3 项乡镇主数据/完整展示、第 4 项真实公众号名称和菜单路径

## 一、修复范围

本地 PR 只处理已确认的修复清单第 1、2 项：

1. 退回终审完成后释放对应电话核验任务，并让默认任务列表只显示真实开放待办。
2. 增加回归测试，覆盖三种终审决定、默认待办过滤和显式历史查询。

未修改乡镇主数据、乡镇展示或公众号运营配置。

## 二、修改前后对比

| 场景 | 修改前 | 修改后 |
|---|---|---|
| 终审通过退回 | 退回单已 `APPROVED`，核验任务仍为 `SUBMITTED` | 核验任务同步转为 `RELEASED`，并递增 `lock_version` |
| 终审驳回退回 | 退回单已 `REJECTED`，核验任务仍为 `SUBMITTED` | 核验任务同步转为 `RELEASED` |
| 终审要求补证 | 退回单进入 `NEED_MORE_EVIDENCE`，上一轮任务仍为 `SUBMITTED` | 上一轮任务转为 `RELEASED`；补证重提后创建新一轮任务 |
| 默认任务列表 | 未传 `status` 时返回全部退回核验任务 | 只返回开放任务，且关联退回单必须仍处于 `VERIFYING` 或 `REVIEWING` |
| 修复前历史脏数据 | 已完结退回单的旧 `SUBMITTED` 任务仍会出现在运营待办 | 默认待办按退回单状态排除，不再污染运营工作台 |
| 历史追溯 | 状态查询与当前待办混在一起 | 显式传入 `status=RELEASED` 或 `status=SUBMITTED` 时仍可查看原始历史 |

## 三、变更文件

- `apps/api/src/services/return_v12.py`：在 `APPROVE`、`REJECT`、`NEED_MORE` 三条终审路径释放当前核验任务。
- `apps/api/src/routers/v12_returns.py`：默认列表同时按开放任务状态和开放退回单状态过滤；显式状态查询保持不变。
- `apps/api/tests/test_v12_return_workflow.py`：新增终审释放断言和默认/显式查询回归测试。

## 四、测试先行证据

新增断言在修复前稳定复现两个问题：

- 终审通过后任务实际仍为 `SUBMITTED`，期望 `RELEASED`。
- 默认列表同时返回已完结退回单的历史 `SUBMITTED` 任务。

完成最小实现后：

- 新增/修改的 4 个目标用例：`4 passed`。
- 完整退回流程测试：`20 passed`。
- 提交后的干净分支全量测试：`825 passed, 10 skipped`。
- Python 编译：`compileall` 通过。
- 补丁格式：`git diff --check` 通过。
- 依赖健康：`pip check` 通过。
- 依赖漏洞：`pip-audit --local` 未发现已知漏洞。
- 敏感信息扫描：变更文件无密码、令牌、API Key 等新增硬编码。

## 五、独立代码评审

### 综合代码评审

- 结论：`APPROVE`
- CRITICAL/HIGH/MEDIUM/LOW：均为 0。
- 核查范围：需求一致性、三种终审分支、幂等与历史查询、RBAC、SQL 查询形态、回归测试充分性。

### 架构反方审查

- 结论：`CLEAR`
- 原先的状态边界泄漏已闭合：终审推进退回单时，同步结束本轮核验任务。
- 默认运营投影能够排除修复前遗留的已完结脏状态；显式历史查询保留原始数据属于审计能力，不是当前待办。

## 六、性能、安全与回滚

- 默认列表仍是两条有界分页 SQL；`verification_tasks.return_request_id` 和 `return_requests.status` 均有索引，没有新增逐行查询或 N+1。
- 权限校验未放宽，仍要求 `verification.read`、`verification.task.read` 或全局权限。
- 无数据库结构迁移、无新依赖、无外部调用。
- 可使用 `git revert fbdf01b` 回滚代码修复。

## 七、本地合并以外的门禁

- 本次不推送远程、不部署生产。
- 如果正式库要求把历史记录的物理任务状态也统一改为 `RELEASED`，应在部署前单独统计影响行数、备份并执行受控数据修复；当前默认运营待办已不会展示这些历史脏行。
- 第 3、4 项仍按用户要求保持待定。
