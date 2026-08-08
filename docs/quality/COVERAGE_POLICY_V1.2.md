# V1.2 测试覆盖率门禁策略

## 目标

覆盖率用于发现没有被自动化测试保护的运行路径，不作为“测试数量”或“代码质量”的替代指标。V1.2 的覆盖率门禁必须与 H05 安全负例、幂等、权限和账务不变量一起执行，不允许通过 omit 高风险运行代码或删除安全测试来提高数字。

## 全局强门禁

Main Release Verification 对 `apps/api/src` 启用 line + branch coverage：

- global line coverage：不得低于 75%；
- global branch coverage：不得低于 75%；
- pytest-cov 综合 fail-under：75%；
- 任一门槛失败均阻断 PR / main verification。

报告输出：

- terminal missing-lines report；
- `dist/coverage/coverage.xml`；
- `dist/coverage/coverage.json`；
- `dist/coverage/critical-coverage.json`。

CI 将 `dist/coverage` 上传为 30 天可追踪 artifact。

## 高风险核心模块

以下模块单独聚合 line / branch coverage：

- `core/auth.py`；
- `services/auth_service.py`；
- `services/rbac.py`；
- `services/points_service.py`；
- `services/return_v12.py`；
- `services/supplier_reward_v12.py`；
- `routers/v12_dispatch.py`。

长期目标：核心聚合 line ≥ 90%、branch ≥ 90%。

H06 第一轮先用真实 CI 生成当前基线。如果核心基线已经达到 90%，直接启用 90% 强门禁；如果不足，则必须先识别缺口并优先补异常、权限、并发、幂等、边界测试，不能为了追数字增加无业务价值断言。最终 H06 评审记录必须写明实测基线与启用的最终阈值。

## 禁止项

不得通过以下方式提高覆盖率：

- omit auth、points、return、reward、dispatch 等高风险运行模块；
- skip / xfail H05 安全负例；
- 只执行“容易覆盖”的测试子集；
- 将不可达或未验证生产路径标记为 pragma no-cover，除非有明确评审理由；
- 用大量无断言/低价值 happy-path 测试替代异常和边界测试。

## 回归原则

覆盖率是最低线，不是目标上限。代码覆盖率即使高于门槛，只要安全负例、账务不变量、迁移、权限或并发测试失败，仍然是 NO-GO。
