# V1.2 测试覆盖率门禁策略

## 目标

覆盖率用于发现没有被自动化测试保护的运行路径，不作为“测试数量”或“代码质量”的替代指标。V1.2 的覆盖率门禁必须与 H05 安全负例、幂等、权限和账务不变量一起执行，不允许通过 omit 高风险运行代码或删除安全测试来提高数字。

## 实测基线

H06 第一轮 Main Release Verification run `31262652850` 在完整 pytest（含 H05 安全负例）下测得：

- global line：79.23%；
- global branch：54.99%；
- pytest-cov line+branch 综合：74.40%；
- critical aggregate line：85.04%；
- critical aggregate branch：63.92%。

第一轮故意以 75% branch 目标运行并被正确阻断，证明门禁不是“配置即全绿”。当前 branch 与 75% 目标存在约 20 个百分点差距，若一次性为了数字补齐会需要覆盖大量低风险分支，不符合 H06 的质量原则。

## 当前强门禁

在不降低当前真实质量的前提下，将实测基线锁定为回归下限：

- global line ≥ 79.0%；
- global branch ≥ 54.5%；
- pytest-cov 综合 fail-under ≥ 74%；
- critical aggregate line ≥ 85.0%；
- critical aggregate branch ≥ 63.5%。

这些阈值均略低于实测值，仅保留小幅统计/舍入余量；任何明显覆盖率下降都会阻断 PR / main verification。

长期目标保持：

- global branch ≥ 75%；
- critical line ≥ 90%；
- critical branch ≥ 90%。

后续新增测试优先覆盖异常、权限、并发、幂等、账务边界，再逐步上调门槛；不得为了追数字增加无业务价值断言。

## 报告与追踪

Main Release Verification 输出：

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

第一轮各模块实测：

- auth.py：line 100%、branch 100%；
- auth_service.py：line 90.49%、branch 73.33%；
- rbac.py：line 92.86%、branch 100%；
- points_service.py：line 87.85%、branch 63.04%；
- return_v12.py：line 88.65%、branch 67.78%；
- supplier_reward_v12.py：line 75.88%、branch 43.68%；
- v12_dispatch.py：line 79.70%、branch 52.63%。

因此下一阶段提高 critical branch 时，应优先补 reward / dispatch / points 的真实边界与异常测试，而不是继续给已 100% 的 auth/rbac 堆重复用例。

## 禁止项

不得通过以下方式提高覆盖率：

- omit auth、points、return、reward、dispatch 等高风险运行模块；
- skip / xfail H05 安全负例；
- 只执行“容易覆盖”的测试子集；
- 将不可达或未验证生产路径标记为 pragma no-cover，除非有明确评审理由；
- 用大量无断言/低价值 happy-path 测试替代异常和边界测试。

## 回归原则

覆盖率是最低线，不是目标上限。代码覆盖率即使高于门槛，只要安全负例、账务不变量、迁移、权限或并发测试失败，仍然是 NO-GO。
