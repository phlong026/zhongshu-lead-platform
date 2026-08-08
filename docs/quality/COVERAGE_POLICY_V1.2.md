# V1.2 测试覆盖率门禁策略

## 目标

覆盖率用于发现没有被自动化测试保护的运行路径，不作为“测试数量”或“代码质量”的替代指标。V1.2 的覆盖率门禁必须与 H05 安全负例、幂等、权限和账务不变量一起执行，不允许通过 omit 高风险运行代码或删除安全测试来提高数字。

## 实测基线

H06 第一轮 Main Release Verification run `31262652850` 在完整 pytest（含 H05 安全负例）下测得：

- global line：79.23%；
- global branch：54.99%；
- pytest-cov line+branch 综合：74.40%。

第一版 critical 集合漏掉了实际承载派发核心规则的 `services/dispatch_v12.py`。下载该 run 的 coverage artifact 后，按完整 critical 集合重新聚合得到：

- critical aggregate line：85.93%；
- critical aggregate branch：64.87%。

第一轮故意以 75% branch 目标运行并被正确阻断，证明门禁不是“配置即全绿”。当前 branch 与 75% 目标存在约 20 个百分点差距，若一次性为了数字补齐会需要覆盖大量低风险分支，不符合 H06 的质量原则。

## 当前强门禁

在不降低当前真实质量的前提下，将实测基线锁定为回归下限：

- global line ≥ 79.0%；
- global branch ≥ 54.5%；
- pytest-cov 综合 fail-under ≥ 74%；
- critical aggregate line ≥ 85.5%；
- critical aggregate branch ≥ 64.5%。

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
- `dist/coverage/critical-coverage.json`；
- `dist/coverage/pytest-output.txt`；
- `dist/coverage/pytest-exit-code.txt`。

CI 将 `dist/coverage` 上传为 30 天可追踪 artifact。即使 pytest 在 report 生成前失败，测试输出和退出码仍会保留下来，避免“门禁失败但无证据”。

## 高风险核心模块

以下模块单独聚合 line / branch coverage：

- `core/auth.py`；
- `services/auth_service.py`；
- `services/rbac.py`；
- `services/points_service.py`；
- `services/return_v12.py`；
- `services/supplier_reward_v12.py`；
- `services/dispatch_v12.py`；
- `routers/v12_dispatch.py`。

第一轮 coverage artifact 中各模块实测：

- auth.py：line 90.91%、branch 83.33%；
- auth_service.py：line 86.13%、branch 66.00%；
- rbac.py：line 97.14%、branch 87.50%；
- points_service.py：line 90.63%、branch 70.00%；
- return_v12.py：line 81.79%、branch 55.93%；
- supplier_reward_v12.py：line 86.13%、branch 62.07%；
- dispatch_v12.py：line 90.09%、branch 68.92%；
- routers/v12_dispatch.py：line 69.23%、branch 50.00%。

因此下一阶段提高 critical branch 时，应优先补 return / dispatch router / reward / auth_service 的真实边界与异常测试，而不是给高覆盖路径堆重复用例。

## 禁止项

不得通过以下方式提高覆盖率：

- omit auth、points、return、reward、dispatch 等高风险运行模块；
- skip / xfail H05 安全负例；
- 只执行“容易覆盖”的测试子集；
- 将不可达或未验证生产路径标记为 pragma no-cover，除非有明确评审理由；
- 用大量无断言/低价值 happy-path 测试替代异常和边界测试。

## 回归原则

覆盖率是最低线，不是目标上限。代码覆盖率即使高于门槛，只要安全负例、账务不变量、迁移、权限或并发测试失败，仍然是 NO-GO。
