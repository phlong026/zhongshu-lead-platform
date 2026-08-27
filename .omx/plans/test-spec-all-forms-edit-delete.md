# 测试规格：全系统表单编辑、安全删除与状态化更正

状态：已批准
日期：2026-08-24
关联 PRD：`.omx/plans/prd-all-forms-edit-delete.md`

## 1. 验证原则

- 先写能够复现缺口的失败测试，再实现，再运行相关全量测试。
- 重点覆盖非法状态、越权直调、并发和审计结果；页面按钮可见性不是充分证据。
- 测试使用显式隔离数据库与配置，不加载可能指向生产的默认 `.env`。
- 迁移按 upgrade → downgrade 可行性评估 → re-upgrade 验证；有损 downgrade 必须明确记录。

## 2. P0 单元测试

### 2.1 派发候选搜索

- 按 `company_name` 大小写/空白归一化过滤。
- 清空关键词恢复原始候选数组。
- 无匹配返回空状态。
- 过滤函数不修改源数组、eligibility、reasons 或排序。

### 2.2 Assignment release

- `PENDING_CLAIM` 成功变为 `RELEASED`。
- `CLAIMED/FOLLOWING/RETURN_PENDING/RETURNED/RELEASED/EXPIRED/COMPLETED` 均拒绝。
- release 记录 `released_at/release_reason`、AssignmentEvent actor 与 AuditLog。
- release 后 Lead 回 `READY_DISPATCH`，且不产生积分扣减流水。
- 重复幂等请求只产生一次状态变化和一次事件。

### 2.3 自定义充值

- `package_id` 与 `custom_points` 都填、都不填均校验失败。
- 固定档金额不匹配失败。
- 自定义积分非正整数或现金非正数失败。
- 自定义充值写正确 `RECHARGE`、business type 和 metadata。
- 自定义充值不改变 `level_code`。
- 请求指纹字段覆盖 company、package/custom points、cash、external reference、note。
- 同 key 同指纹返回原 ledger；同 key 不同指纹 409。

### 2.4 公司编辑

- 基础资料正常更新并审计 before/after。
- masked phone 作为写入值时拒绝。
- 基础资料接口传 service area/capability 字段时拒绝或忽略并告警，不能改变生效资格。
- `ACTIVE -> DISABLED -> ACTIVE` 状态切换正确。

## 3. P1 单元测试

### 3.1 回收站

- 软删除写入 deleted actor、reason、time 和 purge_after。
- 普通列表排除 deleted；回收站只列未 purge 项。
- 恢复清空删除字段并写 restored actor/time。
- purge dry-run 不删数据；apply 只删无下游引用且已到期记录。

### 3.2 FollowUp 更正

- void 保留原记录并写 actor/reason/time。
- correction 追加新记录并关联被更正记录。
- 当前状态取最新有效 followup。
- void 最新 DEAL 后，assignment/lead 投影回最新有效非 DEAL 状态。

### 3.3 ReturnEvidence 作废

- 作废不删除文件 key、sha、size、mime 和原文件名。
- 默认详情与汇总只统计有效证据。
- 作废后证据不足时提交失败或状态回补证。

### 3.4 配置版本

- DRAFT 可编辑、软删、恢复。
- PUBLISHED 的原地 PATCH/DELETE 被拒绝。
- 复制为新 DRAFT 保留来源版本。
- 发布新版后旧版按现有 expires/status 或 RETIRED 退场。

## 4. API 集成与权限测试

- 无 `assignment.release` 权限直调 release 返回 403。
- 无 `points.recharge` 权限直调充值返回 403。
- 无 `company.update/disable/restore` 权限分别返回 403。
- 无 `lead.restore/purge`、`return.evidence.void`、`followup.void` 权限返回 403。
- 每个成功和拒绝的高风险动作均有结构化审计或安全日志。
- RBAC seed、同步脚本和数据库权限集合 exact match。

## 5. 并发和一致性测试

- 同一非空 `external_reference`、不同 key 并发请求只有一个入账，另一个 409。
- 同一 key、不同请求指纹并发请求只有匹配请求可成功。
- 同一 assignment 的 claim 与 release 并发只能一个成功；最终 Lead、Assignment、积分和事件一致。
- 公司服务区待审增加/移除期间，派发资格仍使用当前批准配置；批准后才变化。
- followup void/correction 并发不会产生无法确定的当前状态；使用 `created_at,id` 稳定排序。

## 6. 数据库迁移测试

- 迁移前报告重复非空 `external_reference`；发现重复时阻断添加唯一约束。
- PostgreSQL 建立非空值唯一约束/部分唯一索引。
- SQLite 测试环境具有等价唯一行为，不误伤多个 NULL。
- nullable lifecycle/void 字段 upgrade 成功，旧代码可忽略新列。
- downgrade 是否有损被明确标注；re-upgrade 后数据仍可读。

## 7. 端到端验收

### 管理端派发

1. 打开待人工派发客资。
2. 输入公司名“合家”，列表只显示名称匹配的后端候选。
3. 查看资格、所需积分、可用积分和不可派原因。
4. 选择合格公司派发。
5. 在领取前 release，客资回派发池并可再次派发。
6. 清空搜索恢复完整候选列表。

### 财务充值

1. 输入关键词搜索加盟商公司。
2. 切换自定义模式，输入 12345 积分、实收金额和付款流水。
3. 提交成功，余额增加 12345，等级不变。
4. 原请求重放返回原结果；改金额或换 key 重用流水均返回 409。

### 公司资料

1. 编辑名称/负责人/电话/备注并保存。
2. 停用后公司不再作为有效候选；历史派发仍可查。
3. 恢复后重新符合其他资格时可作为候选。
4. 修改服务区/能力生成待审申请，批准前派发资格不变。

### 草稿回收站

1. 供应商保存草稿并删除。
2. 普通列表不可见，回收站可见。
3. 30 天内恢复并继续编辑提交。
4. dry-run 输出候选但不删除；apply 仅清理到期且无引用草稿。

### 更正和证据

1. 作废错误跟进并补录更正，当前状态重算正确。
2. 作废旧证据并上传新证据，汇总只统计新证据，但旧文件元数据仍可审计。

## 8. 回归、静态与安全检查

- Python compile/static checks。
- 管理端、H5 JavaScript 静态检查。
- 目标测试后运行全部相关 API 测试。
- 浏览器 smoke 与 V1.2 E2E 使用隔离环境。
- 扫描变更文件中的密钥、令牌和调试输出。
- 检查搜索接口分页、列表渲染上限、N+1 和锁顺序。
- 阅读完整 diff，确认 legacy dispatch 未改、财务流水未被原地编辑、服务区未绕审。

## 9. 完成门槛

- 所有新增测试通过，现有相关回归通过。
- 静态检查、类型/编译检查和安全扫描通过。
- 迁移预检与至少一套隔离数据库升级验证通过。
- 关键 E2E 通过；无法运行的外部门禁必须单独列出，不能当作已完成。
- 无已知 P0/P1 错误，审查意见已关闭。
