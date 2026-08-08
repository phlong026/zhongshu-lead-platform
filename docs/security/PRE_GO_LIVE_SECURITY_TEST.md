# V1.2 Pre-Go-Live Security Negative Test Matrix

## 目标

本文件定义正式灰度前必须持续通过的安全负例。原则不是证明 happy path 可用，而是证明攻击者在持有合法低权限账号、可猜测业务 ID、可构造 Token 和可重复请求时，仍不能跨租户读取、修改或制造业务副作用。

## 租户与角色模型

测试至少建立两个互不相关的加盟商公司：

- Target Tenant：持有真实业务对象；
- Attacker Tenant：仅持有合法 `FRANCHISE_OWNER` 账号。

攻击者可以知道目标对象 UUID，但不得因此获得任何读取、修改、领取、审核、结算、文件访问或消息访问能力。

## 必测攻击面

### 1. 多租户 IDOR

必须覆盖：

- assignment detail / claim；
- supplier lead detail；
- return detail / evidence upload；
- supplier reward detail；
- points account / ledger query；
- notification list / mark-read；
- platform report。

预期：403 或 404；错误正文不得包含目标客户手机号、姓名、退回说明、积分余额等摘要信息。

### 2. JWT / Session

必须拒绝：

- 签名篡改 Token；
- 已过期 Token；
- stale `session_version` Token；
- DISABLED User；
- DISABLED Company 下成员的既有 Token。

### 3. OAuth / Invite

必须验证：

- OAuth state 篡改失败；
- OAuth state 过期失败；
- `return_url` 不得形成 open redirect；
- Invite 已使用后不能重放；
- 已绑定公司微信不能利用另一家公司 Invite 改绑。

### 4. 私有文件 Token

必须拒绝：

- Token 篡改；
- Token 过期；
- Evidence A Token 读取 Evidence B；
- User A Token 被 User B 使用；
- 攻击者即使为目标 Evidence 自行生成合法格式 Token，仍必须经过业务租户权限校验。

跨租户 Evidence 上传必须在读取请求文件和写入对象存储之前完成鉴权；403 时不得产生文件或数据库记录副作用。

### 5. 积分安全

必须验证：

- 加盟商不能查询其他公司的积分账户；
- 加盟商即使传入其他 `company_id` 查询流水，也只能得到自身数据；
- 加盟商不能充值、调整、冲正积分；
- 相同 idempotency key 只能产生一次积分变更；
- 任意扣减不得使余额小于 0。

### 6. 退回与奖励

必须验证：

- 加盟商不能执行退回终审；
- 加盟商不能结算或冲正供应商奖励；
- 奖励重复结算不得重复产生积分流水；
- 跨公司 Reward/Return/Evidence 访问必须被拒绝。

### 7. Notification / Report

- 消息列表只能按当前 `user_id/company_id` 返回；
- 对其他租户 notification ID 执行 mark-read 必须返回 404；
- 加盟商不得访问平台级 V1.2 overview report。

### 8. Audit 脱敏

`before_json / after_json / metadata_json` 均不得持久化：

- password；
- raw JWT/token；
- Cookie/Authorization；
- Secret；
- 完整手机号/phone hash/fingerprint。

允许保存明确标记为 `phone_masked` 的掩码值。

## CI 入口

核心自动化文件：

`apps/api/tests/test_pre_go_live_security.py`

该文件必须随全量 `pytest` 在 Main Release Verification 中执行。后续 H06 覆盖率门禁不得排除该测试。

## Go / No-Go

以下任一情况为 `NO-GO`：

- 跨租户可读取或修改业务对象；
- unauthorized 请求在对象存储/数据库产生副作用；
- JWT/OAuth/File Token 可绕过；
- Company/User disable 后旧会话仍可使用；
- 积分可出现重复入账或负余额；
- Reward 重复结算产生多条流水；
- 审计包含认证凭据或明文手机号；
- 安全负例被 skip/xfail 规避。
