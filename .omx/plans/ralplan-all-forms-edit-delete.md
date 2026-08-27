# RALPLAN-DR：全系统表单编辑 / 安全删除 / 状态化更正

状态：已批准（Architect `APPROVE`；Critic `APPROVE`）
日期：2026-08-24
范围：当前生产 V1.2 管理端、加盟商 H5、供客 H5、电销 H5 中会产生持久化业务记录的表单。本文件是后续实施的权威交接方案。

## 0. 关键决策修订摘要

本轮修订将计划收敛为“状态化更正 + 安全作废/归档”的 hybrid 方案：

1. P0 不建设通用 `event` 表；需要查询/过滤的实体（Lead、ReturnRequest、ReturnEvidence、FollowUp、Assignment 等）加 nullable 状态字段，并继续使用现有 `AuditLog` / `AssignmentEvent` / Outbox。
2. P0 派发搜索只改生产 V1.2 管理端 `apps/admin/public/v12-operations.js`；明确排除 legacy `apps/admin/public/app.js` 的旧 dispatch mutation。
3. 跟进记录不可原地编辑；采用 append-only correction，支持 `voided_at/by/reason` 作废旧记录并追加替代记录，当前状态由最新有效跟进投影。
4. 退回证据增加作废字段；有效证据查询过滤 `voided_at IS NULL`，但文件对象、sha、原始元数据继续保留。
5. 增加 V1.2 assignment release endpoint/service：只允许 `PENDING_CLAIM`，其余现有 AssignmentStatus 全部拒绝，领取后改走退回、关闭、奖励冲正。
6. 权限变更必须同步 `ROLE_PERMISSION_MATRIX`、同步脚本和 exact-sync 测试。
7. 加盟商公司不新增 `ARCHIVED`；归档/恢复统一使用现有 `DISABLED` / `ACTIVE`。
8. 迁移只增加 nullable 列；30 天回收站清理是 dry-run/apply 运维 job；产生数据后 downgrade 有损，推荐回滚代码而非删列。

## 1. 需求

### 1.1 用户最初 P0

- 人工派发：候选接收公司必须可搜索、可选择，并保留现有资格判断、积分占用、幂等、审计。
- 人工充值积分：加盟商公司必须可搜索选择；充值积分可选择固定档，也可自定义积分金额；必须保留 `RECHARGE` 流水、唯一付款流水号、幂等、通知、审计。
- 加盟商资料：已保存内容可编辑；涉及服务区域、供客/接客能力的修改必须重新审核，审核前不影响当前有效配置。
- 所有会产生持久化业务记录的表单：增加可解释的编辑、删除/撤回/作废/归档能力。

### 1.2 已确认规则

- 草稿/未提交：可编辑、可软删除；30 天回收站内可恢复，超过后通过运维 job purge。
- 待审/待激活：不可直接篡改已提交事实；允许撤回后编辑再提交，或平台驳回后修改重提。
- 主数据：可编辑；已有引用时不得物理删除，统一 `DISABLED`/`ACTIVE` 归档恢复。
- 已派发/已领取/已完成：不可删除核心记录；只允许释放、关闭、作废或追加更正，且必须审计。
- 积分/奖励流水：只允许冲正，不允许改原流水或删除。
- 审计、派发轨迹、通知：只读。
- 服务区域、供接客资能力：修改进入审核草稿/待审；批准前不影响现有效配置和派发资格。

### 1.3 明确排除

- 登录表单、筛选表单、确认弹窗、只读详情页。
- legacy mutation 恢复或旧派发入口功能扩展；P0 不改 `apps/admin/public/app.js` 的旧 dispatch。
- 在 P0/P1 建通用 event-sourcing 表或重做全站架构。

## 2. 仓库证据与精确行号

### 2.1 生产入口

- V1.2 管理端：`apps/admin/public/v12-operations.js:217-219` 当前人工派发候选弹窗直接列出 `/v1.2/dispatch-pool/{lead_id}/candidates`，无搜索。
- legacy 管理端：`apps/admin/public/app.js:78-79` 有旧 dispatch 入口，P0 明确排除；`apps/admin/public/app.js:141` 当前充值页是固定公司下拉 + 固定档位。
- 生产加盟商工作台：`apps/h5/public/v12-workbench.js:98-121` 公司资料与能力页；`apps/h5/public/v12-workbench.js:198-205` 供客/接收/退回入口；`apps/h5/public/v12-workbench.js:200-203` 派发单详情和新增跟进。
- 生产供客 H5：`apps/h5/public/supplier.js:457-469` 草稿继续填写/删除、驳回修改重提；`apps/h5/public/supplier.js:672-676` 编辑草稿；`apps/h5/public/supplier.js:690-860` 上传/编辑表单。
- 生产电销 H5：`apps/call-h5/public/app.js:231-260` 退回核验任务列表；后续核验提交只按任务状态推进，不属于可删除表单。
- API 静态挂载/入口：`apps/api/src/main.py:175` V1.2 H5 默认跳转到 `/h5/v12-workbench.html`；`apps/api/src/main.py:191` 挂载 `apps/call-h5/public`。

### 2.2 后端现状

- 公司搜索：`apps/api/src/routers/companies.py:21-42` 已支持 `keyword/status/page/page_size`，可复用为充值公司搜索。
- 公司更新：`apps/api/src/routers/companies.py:93-108` 已有 PATCH；`apps/api/src/services/company_service.py:231-251` 当前可直接替换 region/capabilities，需拆分为“基础资料直接改、服务区域/能力进审核”。
- 公司创建：`apps/api/src/services/company_service.py:162-212` 创建公司时会初始化积分账户和待审能力/服务区。
- V1.2 供客草稿：`apps/api/src/routers/v12_lead_supply.py:208-328` supplier lead 创建/更新/删除/提交；`apps/api/src/services/lead_supply_v12.py:130-141` 当前 `discard_draft()` 是物理删除，必须改软删除。
- 平台客资：`apps/api/src/routers/v12_lead_supply.py:112-183` 平台创建/编辑/提交草稿。
- 派发候选与人工派发：`apps/api/src/routers/v12_dispatch.py:172-198` 候选；`apps/api/src/routers/v12_dispatch.py:201-239` 手工派发。
- 派发资格：`apps/api/src/services/dispatch_v12.py:219-260` 资格判断包含公司状态、接收能力、服务区、重复、可用积分。
- 派发服务区语义：`apps/api/src/services/dispatch_v12.py:147-156` 已支持“移除申请待审时当前区域仍有效”。
- 跟进：`apps/api/src/services/followup_service.py:24-72` 当前 append-only 新增跟进并更新 assignment/lead 当前状态；`apps/api/src/services/followup_service.py:75-85` 列表返回当前无 void/correction 字段。
- 充值：`apps/api/src/routers/points.py:181-216` 充值 endpoint；`apps/api/src/schemas/points.py:40-47` `RechargeBody` 当前固定 `package_id`；`apps/api/src/services/points_service.py:210-269` 当前现金金额必须等于固定档。
- 冲正：`apps/api/src/routers/points.py:227-235`、`apps/api/src/services/points_service.py:272-280` 已有积分流水 reverse。
- 退回证据：`apps/api/src/routers/v12_returns.py:88-160` 上传证据；后续详情/汇总必须过滤有效证据。
- RBAC：`apps/api/src/services/rbac.py:15-112` `ROLE_PERMISSION_MATRIX`；其中 `apps/api/src/services/rbac.py:43-64` OPERATION 已含 `assignment.release`，实施需确认 DB exact sync 与权限测试。
- 审计：`apps/api/src/core/models.py:526-543` `AuditLog` 已有 actor/action/resource/payload/ip/user_agent。

## 3. 原则（3-5）

1. 不改历史事实：已影响积分、奖励、派发、核验、通知的记录只能追加更正、冲正、作废或关闭。
2. 状态驱动 UX：按钮由状态 + 权限 + 是否存在下游引用共同决定，前端隐藏只是体验，后端必须拒绝非法直调。
3. 主数据可退场，不物理消失：公司、配置、规则用 `ACTIVE/DISABLED`、版本、retire 管理，避免破坏历史引用。
4. 草稿友好但可清理：草稿可编辑、删除、恢复；30 天后由可审计 job 清理，不在用户请求链路做 hard delete。
5. 配置发布不可篡改：草稿可改，已发布不可原地改；新版发布后旧版用现有 `expires_at/status` 或 `status=RETIRED` 退场。

## 4. 驱动（Top 3）

1. 一线运营效率：派发与充值都需要搜索公司，减少长下拉和误选。
2. 财务/审计正确性：积分与奖励必须可追溯、幂等、可冲正，不可被编辑删除破坏账。
3. 已生效业务安全：服务区域/接客能力修改不能让已审核资格瞬间失效或绕开审核。

## 5. 全实体 / 表单动作矩阵

| 表单/实体 | 当前入口 | 编辑 | 删除/撤回/归档 | 后端契约 | 优先级 |
|---|---|---|---|---|---|
| 人工派发候选公司 | `v12-operations.js:217-219` | 搜索候选公司；选中后显示资格、所需积分、可用积分、不可派原因 | 已派发单不可删；新增 release 仅限领取前 | 复用 candidate 资格；`POST /v1.2/assignments/{id}/release` 只允许安全状态 | P0 |
| 人工充值积分 | `app.js:141` | 公司可搜索；固定档或自定义积分二选一 | 原流水不可删，错账用 reverse | `RechargeBody` 支持 XOR；`external_reference` 唯一幂等；RECHARGE/审计/通知保留 | P0 |
| 加盟商基础资料 | `app.js:83-84`、`companies.py:93-108` | 名称、负责人、电话、备注可编辑 | 用 `DISABLED/ACTIVE` 归档/恢复；不新加 `ARCHIVED` | 有引用公司禁止物理删除；所有变更 audit | P0 |
| 服务区域 / 接客能力 | `v12-workbench.js:98-121`、`company_profile_v12.py:180-317` | 修改生成待审版本/申请 | 撤回待审；已批准配置不删，移除也走审核 | 审批前现有效配置继续参与派发资格 | P0/P1 |
| 供客草稿 Lead | `supplier.js:457-469`、`lead_supply_v12.py:130-141` | DRAFT/INVALID 可编辑重提 | DRAFT 软删除进回收站；30 天 purge job | nullable delete fields；列表默认排除 deleted | P0 |
| 平台录入 Lead | `v12_lead_supply.py:112-183`、`v12-leads.js:74-128` | DRAFT 可编辑，PENDING 可撤回后编辑 | 草稿软删；已派发只关闭/释放/作废 | Lead 增加 lifecycle nullable 字段 | P1 |
| 派发 Assignment | `v12_dispatch.py:201-239`、`dispatch_v12.py` | 核心字段不可编辑 | PENDING_CLAIM 可 release；领取后不可 release | release 需要行锁、审计、通知、积分/奖励联动 | P0/P1 |
| 跟进 FollowUp | `followup_service.py:24-72` | 不原地编辑；追加 correction | 旧记录可 void；或“作废并重建” | 当前状态由最新有效记录投影 | P1 |
| 退回 ReturnRequest | `v12_returns.py:59-511` | DRAFT/NEED_MORE 可补充；REVIEWING 不改事实 | DRAFT 可软删；已审只能关闭/终审 | nullable lifecycle 字段 + audit | P1 |
| 退回证据 ReturnEvidence | `v12_returns.py:88-160` | 不改文件；可重新上传新证据 | 可 void 证据；文件/sha 保留 | 查询/汇总只统计 `voided_at IS NULL` | P1 |
| 电销核验任务 | `call-h5/public/app.js:231-260` | 提交前当前表单可改；提交后只追加复核 | 任务不可删，只关闭/重新分配 | 审计 + 状态机 | P2 |
| 积分流水 | `points_service.py:210-280` | 不编辑 | reverse 冲正 | 保持 RECHARGE/REVERSE，不删除 | P0 |
| 奖励流水 | `v12_rewards.py:107-290` | 不编辑 | reverse/cancel | 原奖励不可删，调整走反向流水/状态 | P1 |
| 配置草稿/规则 | `points.py:57-144`、奖励规则、字典/模板 | DRAFT 可编辑；PUBLISHED 不可改 | DRAFT 软删；PUBLISHED 用现有过期/status 退场 | publish 新版，旧版沿用现有 `expires_at/status` 或 `status=RETIRED` | P1 |
| 审计/轨迹/通知 | AuditLog/AssignmentEvent/Notification | 只读 | 不删 | 可导出/筛选，不提供编辑删除 | P2 |

### 5.1 生产持久化表单覆盖清单

| 生产持久化表单/对象 | 入口/模型线索 | 可编辑动作 | 删除替代动作 | 排除/只读原因 |
|---|---|---|---|---|
| 内部账号基础资料、角色、启停 | `app.js:219-258`、User/UserRole | 基础资料、重置密码、角色调整、启停 | 禁止物理删除；用 `DISABLED/LOCKED` | 登录表单本身排除，账号记录需保留审计 |
| 工作日历 override/reset | `app.js:151-171`、`workday_calendar.py` | override 节假日/工作日说明 | reset 清除 override，回到默认日历 | 日历历史不作为业务流水删除 |
| 字典项 active/version | `DictionaryItem`、`master_data.py` | 新增 version、调整 label/sort/active | `active=false`，不删历史 version | 已引用 code 需可解释 |
| 积分档位 PointsPackage | `PointsPackage`、`points.py:57-144` | 用既有 `effective_at/expires_at/status` 发布新版 | 过期/停用，不物理删 | 已充值流水引用 package snapshot |
| 价格规则 LeadPriceRule | `LeadPriceRule`、`points.py:57-144` | 用既有 `effective_at/expires_at/status` 发布新版 | 过期/停用，不物理删 | 已派发价格需可追溯 |
| 奖励规则 RewardRule | `v12_rewards.py`、`SupplierRewardRule` | `version/status=PUBLISHED|RETIRED/effective_at/published_by` | `status=RETIRED` | 已产生奖励按快照结算 |
| 系统配置 SystemConfig | `SystemConfig`、admin schemas | `version/status=PUBLISHED|RETIRED/effective_at/published_by` | `status=RETIRED` | 配置发布历史需保留 |
| 核验模板 VerificationTemplate | `VerificationTemplate`、`verification_service.py` | 发布新 version | retire 旧版 | 已提交核验任务引用模板 |
| 邀请撤销 | 邀请/绑定记录 | 可重发/补充备注 | revoke/cancel 邀请 | 邀请轨迹保留，不能硬删 |
| 公司能力/服务区撤回 | `company_profile_v12.py:180-317` | 待审申请可撤回后重提 | 已批准配置走移除申请/审核 | 审批前不得影响现有效派发资格 |
| 平台客资 Lead | `v12_lead_supply.py:112-183` | DRAFT 编辑，PENDING 撤回后改 | 草稿软删；已派发关闭/释放/作废 | 已派发后不可破坏链路 |
| 供应商客资 Lead | `supplier.js:457-469`、`lead_supply_v12.py` | DRAFT/INVALID 编辑重提 | 草稿软删进回收站 | 当前物理删除需改软删 |
| FollowUp | `followup_service.py:24-72` | append-only correction | void 原记录；不硬删 | 跟进历史是业务事实 |
| ReturnRequest | `v12_returns.py:59-511` | DRAFT/NEED_MORE 补充 | DRAFT 软删；已审关闭/终审 | 已审结论不可篡改 |
| ReturnEvidence | `v12_returns.py:88-160` | 上传新证据 | void 证据，文件/sha 保留 | 文件证据需留痕 |
| Verification task/submission | `call-h5/public/app.js:231-260`、VerificationTask | 领取/提交前按任务状态推进 | release/cancel/reassign | 提交后不可改历史核验 |
| Assignment | `AssignmentStatus` | 核心字段不可编辑 | 仅 `PENDING_CLAIM` release；其他状态拒绝 | 领取后涉及隐私、扣点、奖励 |
| Ledger/Reward | PointsLedger/SupplierLeadReward | 不编辑原流水 | reverse/cancel/reversal | 财务与奖励事实不可改删 |
| Audit/Outbox/Notification | AuditLog/Outbox/Notification | 只读/重试通知 | 不删；必要时标记处理状态 | 审计和投递轨迹必须保留 |

## 6. 具体生命周期字段与语义

### 6.1 草稿 30 天回收站字段

对可草稿删除实体（Lead、ReturnRequest、配置 Draft 等）增加 nullable 字段：

- `deleted_at`: 软删除时间。
- `deleted_by`: 操作人。
- `delete_reason`: 删除原因。
- `restored_at`: 最近恢复时间。
- `restored_by`: 最近恢复人。
- `purge_after`: 默认 `deleted_at + interval '30 days'`，便于 job 查询和人工审计。

不对公司新增回收站字段；公司归档恢复使用 `status=DISABLED/ACTIVE`，历史引用继续可查。

### 6.2 list / restore / purge 过滤

- 普通列表默认：`deleted_at IS NULL`。
- 回收站列表：`deleted_at IS NOT NULL AND purge_after > now()`；可增加 `include_expired=true` 仅管理员查看待清理项。
- restore：仅对未 purge 的草稿/可补正状态开放；清空 `deleted_at/deleted_by/delete_reason/purge_after`，写 `restored_at/restored_by` 和 audit。
- purge job：命令默认 dry-run，输出候选数量和阻塞原因；只有 `--apply` 才物理删除。仅清理无下游 assignment/return/reward/ledger 约束的软删草稿。生产先 dry-run 导出，再审批 apply。
- downgrade：产生软删数据后删列会丢失生命周期事实，因此数据库 downgrade 标记为有损；回滚优先禁用代码路径并保留列。

### 6.3 待审撤回/重提

- PENDING/PENDING_REVIEW 可走 `withdraw`，生成 `withdrawn_at/by/reason`，状态回到 DRAFT 或 INVALID。
- 重提写新 `submitted_at/submitted_by`，原审核意见保留在 audit/review_note 历史，不覆盖历史审计。

## 7. P0 详细设计

### 7.1 派发候选公司可搜索

前端只改 `apps/admin/public/v12-operations.js`：

- 在候选弹窗顶部增加搜索框，仅对已经返回的候选列表做前端本地过滤。
- 最小搜索字段：`company_name`；如候选响应已含非敏感展示字段，可附带过滤，但不搜索负责人/手机号，不新增敏感字段。
- 不扩展 candidates API，不新增 `keyword/page/page_size`，不改后端资格计算。
- 清空搜索恢复全量候选；无匹配时显示空结果提示。
- 选中公司后展示：是否可派、所需积分、可用积分、服务区匹配、重复/能力/积分不足原因。
- 手工派发继续使用当前 `Idempotency-Key` 语义。

后端：

- P0 不改 `GET /api/v1/v1.2/dispatch-pool/{lead_id}/candidates`；候选集合和 eligibility 全量由现有后端返回。
- 本地过滤不得改变候选集合来源、排序含义或资格判定，只改变当前弹窗展示子集。
- 负向测试必须覆盖：无接客能力、服务区域不匹配、积分不足、公司 `DISABLED`、自供自接、重复接收方。

排除：

- 不改 `apps/admin/public/app.js:78-79` 旧 dispatch；旧 mutation 不恢复、不增强。

### 7.2 Assignment release endpoint/service

新增 endpoint：

- `POST /api/v1/v1.2/assignments/{assignment_id}/release`
- 权限：`assignment.release`；若复用现有 OPERATION 权限，仍要跑 exact-sync 测试确认 DB 与 `ROLE_PERMISSION_MATRIX` 一致。
- Body：`reason`、可选 `idempotency_key`。

状态规则：

- 允许：仅 `PENDING_CLAIM`。
- 拒绝：现有其余 AssignmentStatus 全部拒绝，即 `CLAIMED`、`FOLLOWING`、`RETURN_PENDING`、`RETURNED`、`RELEASED`、`EXPIRED`、`COMPLETED` 返回 409，并提示使用退回/关闭/奖励冲正。

联动：

- 行锁锁定 Assignment、Lead、PointsAccount（如需要校验可用占用）、相关 Reward。
- 将 Assignment 置为 `RELEASED`，可写 `released_at/release_reason`；不新增 `released_by` 字段，释放人由 `AssignmentEvent.actor_user_id` 与 AuditLog 记录。
- 若 Lead 的当前活跃 assignment 指向该单，则 Lead 回到 `READY_DISPATCH`，清空/更新当前 assignment 投影。
- 积分：当前实现领取时才真正扣点；`PENDING_CLAIM` release 不创建积分 ledger，只释放占用投影。若未来存在预扣 ledger，必须创建反向 ledger 而不是直接改账。
- 奖励：V1.2 奖励通常在领取后产生；release 若发现领取前异常 reward，则置 `CANCELLED` 并 audit；领取后已有 reward 时拒绝 release，改走奖励 reverse/return flow。
- 写 `AssignmentEvent(RELEASED)`、AuditLog、站内通知/Outbox。

### 7.3 充值公司搜索 + 自定义充值积分

前端：

- 充值页公司选择从固定 select 改为 searchable combobox，复用 `/companies?keyword=&status=ACTIVE&page_size=20`。
- 充值档位分为：
  - 固定档：选择 `package_id`。
  - 自定义：输入 `custom_points` 和线下实收 `cash_amount_cents`。
- 显示幂等约束：付款流水号必填且唯一，重复提交返回既有结果。

后端 `RechargeBody` 语义：

- XOR：`package_id` 与 `custom_points` 必须且只能填一个。
- 固定档：`cash_amount_cents` 必须等于 package 金额；积分 = `base_points + bonus_points`；保持现有等级/档位规则。
- 自定义：`custom_points` 为正整数；`cash_amount_cents` 表示实际线下收款金额，原则上 `> 0`，如业务允许赠送需另设 `MANUAL_GRANT` 权限，不混入充值。
- 自定义不改变公司等级/套餐权益，ledger `type=RECHARGE`，`business_type=POINTS_CUSTOM_RECHARGE`，metadata 记录 `{custom_points, cash_amount_cents, external_reference, note}`。
- `idempotency_key` 定死：相同 key 仅在请求指纹完全一致时返回原 ledger；同 key 但 company/package/custom_points/cash_amount/external_reference/note 任一不同，返回 409。
- `external_reference` 定死：非空付款流水号全局唯一；任何重复 `external_reference` + 不同 `idempotency_key` 一律 409，不允许“换 key 重放”。
- 并发安全：规划数据库层非空 `external_reference` 唯一索引/约束；迁移前先跑重复检查，发现重复需人工冲正/合并后再加约束。
- 通知、审计、Outbox 不降级。

测试重点：

- XOR 负例：两者都填、都不填。
- fixed package 金额不匹配拒绝。
- custom points 并发相同付款流水只入账一次。
- 相同 `idempotency_key` 不同请求指纹返回 409。
- 相同 `external_reference` 不同 key 返回 409；迁移前重复数据检查可阻止上线。
- custom recharge 不触发 level_code 变化。

### 7.4 加盟商资料编辑

- 基础资料（名称、负责人、手机号、备注）可 PATCH；手机号显示与返回需持续脱敏，不能把 masked phone 当完整手机号写回。
- 公司归档：`ACTIVE -> DISABLED`；恢复：`DISABLED -> ACTIVE`。不新增 `ARCHIVED`。
- 若公司有未完成 assignment、待处理退回、未结算奖励，归档前给出阻塞或强确认策略；但历史记录仍引用公司并可查。
- 服务区域、供客/接客能力修改必须走 `company_profile_v12` 审核模型，禁止继续通过 `company_service.py:231-251` 直接替换已生效范围。

## 8. P1/P2 详细设计

### 8.1 FollowUp append-only correction

字段：

- `voided_at`
- `voided_by`
- `void_reason`
- `corrects_followup_id`（新 correction 记录可指向被更正记录）

操作：

- `POST /followups/{id}/void`：仅创建人或有运营权限可作废，必须给原因。
- `POST /followups/{id}/corrections`：先 void 原记录，再 append 新记录；或仅 append correction 并在投影时覆盖，以实现为准，P1 推荐“作废并重建”更直观。

状态投影算法：

1. 查询 assignment 下 `voided_at IS NULL` 的 followups。
2. 按 `created_at DESC, id DESC` 取最新有效记录。
3. `assignment.current_follow_status` / `lead.current_follow_status` 投影为该记录 status；若无有效记录，回退为 assignment 状态的默认展示。
4. 若最新有效 status 为 `DEAL`，assignment/lead 可投影完成/关闭；若 DEAL 被 void，必须重算回最新有效非 DEAL 状态，并写 audit。

### 8.2 ReturnEvidence void

字段：

- `voided_at`
- `voided_by`
- `void_reason`

语义：

- 上传文件不可改；作废只影响业务有效性。
- 详情、汇总、提交前证据充分性校验只统计 `voided_at IS NULL`。
- 存储对象 key、size、mime、sha256、original_filename 保留，便于审计和争议复核。
- 证据作废后若有效证据不足，ReturnRequest 回到 `NEED_MORE_EVIDENCE` 或禁止提交。

### 8.3 ReturnRequest / Lead 安全删除

- DRAFT 可软删入回收站。
- PENDING/REVIEWING 先 withdraw 或 reject-to-edit，不直接删。
- APPROVED/REJECTED/COMPLETED 只读，必要时追加复核/冲正。

### 8.4 配置草稿、发布新版、retire

适用：积分套餐、价格规则、奖励规则、字典/审核模板、系统业务参数。

- DRAFT：可编辑、可软删、可恢复。
- PUBLISHED：不可原地编辑；“编辑”动作复制为新 DRAFT。
- PointsPackage / LeadPriceRule：沿用既有 `effective_at`、`expires_at`、`status`，发布新版时设置新版 `effective_at`，旧版用 `expires_at/status` 退场。
- SystemConfig / RewardRule：沿用 `version`、`status=PUBLISHED|RETIRED`、`effective_at`、`published_by`；不新增 `effective_from/effective_to/retired_at`。
- Retire：已发布配置不可删除，只能通过现有 status/过期字段退场；历史业务继续引用 snapshot/version。
- 回滚：通过发布上一版拷贝或 retire 新版实现，不修改历史版本。

## 9. 方案对比

### 方案 A：最小补丁

- 内容：只加派发搜索、充值搜索/自定义、公司编辑按钮，少量接口补充。
- 优点：最快。
- 缺点：无法统一解决删除/编辑边界；草稿物理删除、服务区绕审风险、跟进/证据更正缺失仍在。
- 结论：不足以覆盖“所有表单编辑删除”。

### 方案 B：通用事件表/全量 event sourcing

- 内容：所有修改/删除都进入统一 event 表，由投影生成当前状态。
- 优点：审计最完整。
- 缺点：对 V1.2 太重，迁移风险大；Architect 明确不建议 P0/P1 建通用 event 表。
- 结论：拒绝。

### 方案 C（推荐）：hybrid lifecycle + entity nullable + 现有 audit

- 内容：草稿/待审/主数据/流水/轨迹按实体状态字段与现有 audit 管理；P0 解决派发、充值、公司；P1 扩展跟进、证据、配置版本。
- 优点：契合当前模型；迁移可控；可测试；不会重构过度。
- 缺点：需要逐实体补齐投影与负向测试，不能“一张表解决全部”。
- 结论：推荐实施。

## 10. 分阶段实施

### Phase 0：基线保护

- 补充当前行为测试：派发候选、手工派发幂等、充值固定档、供客草稿删除、公司服务区审核。
- 锁定 legacy dispatch 不变，避免误改 `app.js` 旧入口。

### Phase 1：P0 运营闭环

- `v12-operations.js` 派发候选本地搜索过滤。
- candidates API 保持不变，验证本地过滤不改变候选集合/资格判定。
- assignment release endpoint/service。
- 充值公司搜索 + custom recharge XOR。
- 公司基础资料编辑；服务区/能力修改拆到审核流。
- RBAC matrix / sync / exact tests。

### Phase 2：草稿回收站与状态化删除

- Lead / ReturnRequest / config draft nullable lifecycle columns。
- list/restore/recycle-bin/purge job dry-run/apply。
- 迁移与回滚说明上线。

### Phase 3：更正能力

- FollowUp void/correction + 状态投影重算。
- ReturnEvidence void + 有效证据过滤。
- ReturnRequest 补证/撤回/重提完善。

### Phase 4：配置版本化

- DRAFT/PUBLISHED/RETIRED 配置生命周期。
- 发布新版、retire、历史 snapshot 校验。

## 11. 迁移 / 回滚

- 所有 schema 迁移只新增 nullable 列或索引，不在同一迁移里删除列/改类型。
- 对大表按 add nullable → backfill default if needed → app read/write → optional constraint 的顺序。
- 30 天 purge 不由迁移触发；由独立 job 执行，默认 dry-run。
- custom recharge 上线迁移允许增加“非空 `external_reference` 唯一索引/约束”；迁移前必须输出重复检查报告并阻断有冲突环境。
- 回滚策略：
  - 代码回滚：新字段保留，旧代码忽略。
  - 数据回滚：对新写入的 soft delete/void/release/custom recharge 只能用业务反向操作或审计脚本；已产生数据后 downgrade 删列有损。
  - release/custom recharge 上线前需备份数据库并记录迁移版本。

## 12. RBAC / 审计

- 新/确认权限：
  - `assignment.release`
  - `company.update`
  - `company.disable`
  - `company.restore`
  - `lead.restore`
  - `lead.purge`
  - `return.evidence.void`
  - `followup.void`
  - `config.version.manage`
- 实施时必须更新：
  - `apps/api/src/services/rbac.py:15-112`
  - `scripts/sync_rbac.py`
  - `apps/api/tests/test_rbac_exact_sync.py`
  - `apps/api/tests/test_sync_rbac_cli.py`
- 每个 destructive-like 动作必须写 AuditLog：actor、resource、before/after、reason、request_id/ip/user_agent。
- 前端按钮权限不作为安全边界；后端 direct API 测试必须覆盖越权。

## 13. 90% 可测试验收

1. 运营可在 V1.2 派发弹窗按公司名本地过滤候选公司，候选资格说明准确；非法候选不可派发。
2. P0 未修改 legacy `app.js` dispatch mutation。
3. 本地过滤不改变后端候选集合、排序来源和 eligibility 判定；清空搜索恢复全量候选，空结果有提示。
4. PENDING_CLAIM assignment 可 release 回派发池；CLAIMED/FOLLOWING/RETURN_PENDING/RETURNED/RELEASED/EXPIRED/COMPLETED release 返回 409。
5. release 后无积分扣减流水；如未来预扣存在，必须以反向流水释放。
6. 充值公司可搜索；固定档与自定义积分 XOR；付款流水号重复不会重复入账。
7. 相同 idempotency_key 只有请求指纹完全一致才幂等返回；不同指纹 409。
8. 非空 external_reference 有数据库唯一约束；重复 external_reference + 不同 key 一律 409。
9. 自定义充值写 `RECHARGE` ledger，metadata 完整，通知与审计存在。
10. 公司基础资料可编辑；服务区/能力变更在审核前不影响派发资格。
11. 公司归档用 `DISABLED`，恢复用 `ACTIVE`，无 `ARCHIVED`。
12. 供客草稿删除后普通列表不可见，回收站可见，30 天内可恢复。
13. purge job dry-run 不删数据；apply 只删合格草稿并输出审计结果。
14. FollowUp correction 不改旧记录，作废旧记录后当前状态按最新有效记录投影。
15. ReturnEvidence 作废后证据汇总减少，但文件/sha 仍可审计。
16. 审计/通知/派发轨迹无编辑删除入口。

## 14. 测试计划

### Unit

- `RechargeBody` XOR 校验、固定档金额校验、自定义金额/积分边界。
- 派发候选本地过滤纯函数：按 `company_name` 过滤，清空恢复全量，不修改 candidate eligibility。
- `release_assignment()` 状态机、积分占用、reward 异常处理。
- recharge request fingerprint 生成与 idempotency 冲突判断。
- soft delete restore/purge eligibility。
- followup projection：void DEAL 后重算。
- evidence summary 过滤 voided evidence。

### Integration / Direct API

- 越权 direct API：无 `assignment.release`、无 `points.recharge`、无 `return.evidence.void` 返回 403。
- 并发：同一付款流水号并发 custom recharge 只生成一条 ledger。
- 并发：相同 idempotency_key 不同 payload、相同 external_reference 不同 key 均 409。
- 迁移：非空 external_reference 唯一索引前重复检查；存在重复时 migration/preflight 失败。
- 并发：同一 assignment release 与 claim 同时发生，只能一个成功。
- 脱敏：masked phone 不可被当完整手机号 PATCH 回写。
- 服务区域资格：待审新增/移除不改变当前派发资格；批准后才变化。
- 证据作废：作废后提交校验不足证据失败。

### E2E

- 管理端派发：按公司名搜索“合家” → 选公司 → 派发 → release → 再派发；清空搜索恢复全量候选。
- 财务充值：搜索公司 → 自定义 12345 积分 → 填线下流水 → 成功 → 重放幂等。
- 加盟商 H5：草稿保存 → 删除 → 回收站恢复 → 提交审核。
- 供客 H5：驳回后修改重提；手机号重新填写不泄露完整旧号码。
- 电销 H5：只验证退回证据 void 后任务证据数变化，不增加编辑历史任务。

### Observability

- 结构化日志：release/custom recharge/purge/apply/void/correction。
- 指标：release 成功/拒绝数、自定义充值笔数、purge dry-run 候选数、restore 成功数、void evidence 数。
- 告警：custom recharge 幂等冲突、release 与 claim 冲突、purge blocked 异常上升。

## 15. Pre-mortem

1. 自定义充值造成财务错账：若允许 `cash_amount_cents=0` 或重复流水入账，会导致余额失真。预防：XOR、唯一 reference、并发锁、reverse-only 修正。
2. release 与 claim 竞态：运营释放时加盟商同时领取，可能出现 Lead 回池但已扣点。预防：行锁 + 状态条件更新 + 409 冲突 + 幂等 key。
3. 服务区编辑绕过审核：复用公司 PATCH 直接替换 region_codes 会立刻影响派发资格。预防：基础资料 PATCH 与 service area request 分离；资格查询只看 approved/有效 pending removal。

## 16. ADR

### Decision

采用 hybrid lifecycle：实体 nullable 状态字段 + 现有 audit/event/outbox；P0/P1 不引入通用 event table。

### Drivers

- 快速修复运营 P0。
- 保持财务/派发/奖励不可篡改。
- 控制迁移与回滚风险。

### Alternatives considered

- 最小 UI 补丁：快但覆盖不足。
- 全量 event sourcing：审计强但过重。

### Why chosen

当前仓库已有 AuditLog、AssignmentEvent、Outbox、状态机和 entity model；给需要查询的实体补 nullable 字段即可支撑列表过滤、恢复、作废、投影重算，风险低于重构。

### Consequences

- 每个实体需要明确状态字段和过滤语义。
- 投影重算需要测试保障。
- downgrade 删列在产生数据后有损。

### Follow-ups

- P2 可评估是否把多实体操作审计抽象为统一 helper，但不是 P0/P1 前置。
- 配置版本化完成后整理一份业务操作手册。

## 17. 风险

- 充值页面目前在 legacy admin `app.js`，若后续迁到 V1.2 operations，需要避免重复实现。
- `company_service.update_company()` 当前可直接替换服务区/能力，实施时必须拆权限/接口。
- 旧 H5 `apps/h5/public/app.js` 不是当前 V1.2 生产入口，不能按旧页面验收。
- purge 是真正删除，必须保持 dry-run 默认和审批。
- RBAC 数据库与代码 matrix 不一致会造成按钮可见但 API 403，必须 exact-sync。

## 18. 执行分工建议

- Backend lane：迁移、service 状态机、release/custom recharge/soft delete/void/correction API。
- Frontend lane：V1.2 管理端派发搜索、充值搜索/自定义、公司编辑/归档、回收站 UI；生产 H5 只改 v12-workbench/supplier/call-h5。
- Test lane：unit/integration/e2e/并发/越权/脱敏/服务区资格/证据作废。
- Verification lane：RBAC exact sync、迁移 dry-run、日志/指标、生产禁用 legacy mutation 核查。

## 19. 推荐下一步

进入实施前，先由执行方把 Phase 1 拆成 3 个独立 PR：

1. 派发搜索 + assignment release。
2. 充值搜索 + custom recharge。
3. 公司资料编辑 + 服务区/能力审核隔离。

每个 PR 必须带对应 direct API 负向测试和至少一个前端 smoke/e2e 验收。
