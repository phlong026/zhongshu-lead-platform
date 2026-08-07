# 众墅之家客资平台 V1.2 安全审计报告

- 版本：`V1.2.0`
- 日期：2026-08-07
- 范围：应用代码、RBAC、敏感字段、数据库迁移、积分账务、外部集成、对象存储、生产配置、容器/Nginx、发布包与运行手册
- 结论边界：代码级安全控制已建立；本报告不替代第三方渗透测试、云资源安全基线、法务/隐私评估或真实生产演练

## 1. 总体风险结论

V1.2 的高风险面主要集中在：客户手机号与沟通证据、加盟商跨公司数据隔离、积分不可变账务、供应奖励结算、微信/飞书外部凭据、历史手机号迁移、对象存储访问以及生产镜像/数据库配置。

代码层采用 fail-closed 原则：生产 mock、弱密钥、SQLite 回退、未知历史状态、账务语义不一致、未固定的最终镜像、迁移失败或数据对账失败均应阻断 Go/No-Go。

最终安全 `GO` 仍要求发布分支质量/数据库/浏览器三组 CI 全绿，并在目标环境完成真实微信、对象存储、恢复、告警、UAT 和灰度验证。

## 2. 身份认证与会话

已实施控制：

- 内部账号密码使用 Argon2；
- Access Token 使用 HS256 JWT，包含用户 ID、session version、角色与过期时间；
- 公司/用户禁用会提升 session version，使旧 token 失效；
- 微信绑定使用服务端签名 state 与受控回调；
- API 响应使用 `Cache-Control: no-store`，降低含敏感业务数据的浏览器缓存风险；
- 生产环境要求 HTTPS、可信 Host 和明确 CORS Origin。

仍需现场验证：

- 服务号真实 OAuth 域名、回调、OpenID 绑定、Cookie 行为；
- 管理账号 MFA/企业 SSO（当前版本若未接入，应通过运维账号策略与最小权限补偿）；
- 管理员账号生命周期、离职禁用和密钥轮换流程。

## 3. RBAC 与多租户隔离

V1.2 使用服务端 RBAC 和公司边界，不依赖前端隐藏：

- 平台管理、运营、财务、电销、退回审核、加盟商等角色按 permission code 授权；
- 加盟商读取客资时必须存在属于本公司的派发关系；
- 领取前手机号仅返回脱敏结果，领取成功后才允许解锁；
- 财务余额与积分字段按权限单独投影；
- V1.2 报表、审计和追踪接口区分平台权限与“仅本公司”权限；
- 审计快照递归清除 phone/mobile/auth/token/secret/cookie 等敏感键；
- 跨公司通知深链最终仍由后端权限校验，不能通过 URL 获得额外授权。

发布前必须继续执行越权负例：不同加盟商交叉读取客资、证据、积分、奖励、通知和追踪均应返回 403/404 且不泄露摘要。

## 4. 客户手机号与历史指纹

敏感数据采用两种不同用途的 HMAC：

- `PHONE_HASH_SECRET`：兼容历史 V1.0.1 手机号哈希；
- `PHONE_FINGERPRINT_SECRET`：V1.2 90/180/365 天去重指纹。

生产校验强制两把密钥相互独立，并要求 V1.2 指纹密钥足够长度。手机号原文使用字段加密保存；迁移回填只在内存中解密、规范化和计算 HMAC，检查点仅保存业务 ID、游标和错误码，不保存明文手机号。

Preflight 与迁移报告对 `DATABASE_URL`、数据库口令、Token、Secret、Access Key 进行脱敏。

## 5. 数据迁移安全

T30 迁移采用：

- 维护窗口写入冻结；
- V1.0.1 无 PII 基线；
- 先 Alembic 升级，再执行 V1.2 扫描；
- PostgreSQL Advisory Lock + 迁移检查点；
- 有界分页和每批提交；
- dry-run；
- 失败行阻断；
- 生产 reset 双重确认；
- 未知历史状态 strict mapping，禁止静默归入终态；
- 迁移前后 JSON 证据固定写入宿主机 `dist/`。

任何解密失败、未知状态、重复有效派发、账务语义异常或证据元数据异常均为 `NO-GO`。

## 6. 积分与奖励账务

积分安全不是只检查余额，而是验证不可变流水与业务事实：

- 领取使用行锁、状态重检和幂等流水，仅扣一次；
- 人工派发阶段只预留可用积分，不提前扣款；
- 退回批准返分使用独立幂等键，并关联原领取扣分流水；
- 供应奖励仅在 3 个工作日观察期结束且不存在有效申诉时结算；
- 奖励冲正仅允许已结算奖励且限定异常原因；
- 结算和冲正均锁定 reward/points account，并使用唯一幂等键；
- reconciliation 验证账户余额、delta 汇总和最新 `balance_after`；
- reconciliation 进一步验证奖励/冲正/返分流水的公司、类型、业务 ID、金额和 related ledger 语义，防止“流水存在但指错业务”的假一致。

生产发现账务差异时必须立即停止领取、返分和奖励结算入口，保留原始流水与审计证据。

## 7. 并发与幂等

主要控制：

- 人工派发锁客资并重新计算候选资格；
- PostgreSQL 部分唯一索引保证同一客资最多一个有效派发；
- 派发 idempotency key 唯一；
- 领取锁派发单与积分账户，扣分流水具有公司 + idempotency key 唯一约束；
- 退回申请对 assignment 唯一，终审在请求、派发和奖励对象上使用行锁；
- 奖励结算/冲正锁 reward 和 points account；
- 通知 Outbox `event_key` 唯一，重复投影不重复发送业务事件；
- 历史指纹迁移在 PostgreSQL 使用 advisory transaction lock 串行化写者。

Release PostgreSQL 门禁必须验证相关 DDL/唯一约束和迁移；目标环境仍需根据真实并发量完成压力与锁等待测试。

## 8. 飞书集成

飞书改为显式开关：

- `FEISHU_ENABLED=false` 时读取、Token、分页、同步和回写均运行时返回 503，不发外部网络请求；
- `FEISHU_DEV_MOCK=true` 在 production 被拒绝；
- 启用时 App ID/Secret/Token/Table 必须齐全；
- Token 仅保存在进程内并按过期时间刷新；
- 429/5xx 采用有界重试；
- 状态回写失败计数，不把凭据写入诊断响应。

生产启用飞书时仍需验证企业应用最小权限、API 限流和字段映射。

## 9. 微信与通知

- production 禁止 `WECHAT_DEV_MOCK`；
- App ID/Secret 和同域 HTTPS OAuth 回调为生产必填；
- 站内消息和 Outbox 在业务事务中建立，并使用事件键幂等；
- 外部微信发送失败由 Outbox 重试，不回滚已提交的核心业务事实；
- 通知深链只提供导航，不承担授权。

真实服务号消息模板、OpenID、额度、失败码和不同微信客户端必须在 Gate 0/UAT 验证。

## 10. 对象存储与证据

- 生产支持 `s3` 私有对象存储；
- AWS S3 可留空 endpoint 使用 SDK 区域默认地址；
- 自定义 S3/COS/OSS endpoint 必须为 HTTPS；
- Access Key、Secret、Bucket、Region 在生产校验中强制配置；
- 退回证据元数据记录 object key、文件大小和 SHA-256；
- reconciliation 要求 object key 非空、SHA-256 为 64 位、文件大小 > 0。

代码仓库校验无法证明真实桶 ACL/Policy。生产必须验证禁止公共读、服务账号最小权限、版本/生命周期、服务端加密、恢复能力和授权下载。

## 11. 容器、数据库与反向代理

生产 Compose 控制包括：

- API / Scheduler `read_only: true`；
- `no-new-privileges:true`；
- `cap_drop: ALL`；
- tmpfs 只用于必要临时目录；
- API 不向宿主机直接暴露服务端口，由 Nginx 代理；
- PostgreSQL 不对公网开放；
- Nginx 强制 HTTP→HTTPS、HSTS/CSP 等安全响应头、请求限流和 25MB 上传上限；
- `AUTO_CREATE_SCHEMA=false`，生产结构只允许 Alembic；
- API 默认 `RUN_DB_MIGRATIONS=false`，防止多实例启动竞争迁移。

数据库组件通过 `POSTGRES_*` 传入容器，`docker/prepare-env.sh` 使用 URL 编码生成 SQLAlchemy `DATABASE_URL`，避免保留字符导致连接串解析偏差。

## 12. 供应链与镜像完整性

发布门禁包括：

- `pip check`；
- `pip-audit`；
- 仓库密钥扫描；
- 仅 Git tracked 文件进入源码包；
- `.env`、数据库、备份和真实证据文件不进入发布包；
- Release Manifest 与 SHA-256 校验和；
- 最终 Go/No-Go 要求 `APP_IMAGE=仓库:APP_VERSION@sha256:digest`；
- 镜像 tag 必须与 `APP_VERSION` 完全一致；
- `docker image inspect` 的 OCI `org.opencontainers.image.version` 必须与 `APP_VERSION` 完全一致。

仍建议在镜像仓库启用漏洞扫描、签名/证明（如组织具备相关能力）和镜像保留策略。

## 13. 自动评审发现并修复的问题

Sprint 6 自动评审已推动修复以下问题：

- V1.2 扫描早于 schema upgrade；
- AWS S3 默认 endpoint 被错误强制；
- `FEISHU_ENABLED` 只校验不阻断运行；
- Docker Preflight 可能误连宿主机 SQLite；
- `run --rm` 导致 reconciliation 证据丢失；
- 奖励/返分 reconciliation 只检查 ledger ID 非空而不检查业务语义；
- pre-backfill reconciliation 失败码可能被 `|| true` 吞掉；
- Compose 原始数据库 URL 插值与特殊字符编码不一致；
- `APP_IMAGE` 仅做 `1.2.` 子串匹配，无法保证镜像和应用版本一致。

所有 P1/P2 项必须在最终合并前回复、关闭，并再次触发最新 head 的 Codex 评审。

## 14. 尚未完成的目标环境安全验证

以下不能由仓库自动化替代：

- 第三方或独立人员渗透测试；
- 云主机/COS/OSS/S3/PostgreSQL 的实际 IAM、网络 ACL、安全组和审计日志；
- 真实微信 OAuth、通知、跨公司深链攻击测试；
- 生产数据库全量迁移期间的锁等待和资源压力；
- 联合备份恢复演练；
- 隐私影响评估、电话录音授权和数据保留规则；
- 灰度期间的异常检测和应急响应。

这些项目必须在 `V1.2_GO_NO_GO.md` 中签字后才能全量开放。
