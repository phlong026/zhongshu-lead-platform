# 合家美宅客资平台 V1.2.5 生产上线检查表

所有 P0 项必须有证据并由责任人签字。任何一项失败均为 `NO-GO`。

检查证据必须注明属于 `代码完成`、`自动化通过` 或 `真实环境验收`；前两类证据不能勾选第三类现场门禁。

## A. 版本和质量

- [ ] 上线提交来自 `release/v1.2.5`，对应受保护的 V1.2.5 tag；
- [ ] PR 与 Release CI 的全量测试、PostgreSQL 迁移和 Chromium 浏览器任务全部通过；
- [ ] PR 无未解决的 Critical/High/P1/P2 评审问题；
- [ ] `APP_VERSION=1.2.5`，Dockerfile 默认 `APP_VERSION=1.2.5`；
- [ ] `APP_IMAGE` 采用 `repo:APP_VERSION@sha256:digest`，显式 tag 与 `APP_VERSION` 完全一致；
- [ ] `docker image inspect` 的 OCI `org.opencontainers.image.version` 与 `APP_VERSION` 完全一致；
- [ ] README、部署、迁移、回滚、UAT、测试、安全审计和发布说明均为 V1.2；
- [ ] 全角色初始化按 `docs/runbooks/V1.2_INITIALIZATION_SOP.md` 演练，冻结步骤保持未执行且有记录；
- [ ] Main Release Verification 的 global/critical line+branch coverage 门禁通过并保留 coverage artifact；
- [ ] Security Analysis 对当前提交的 Semgrep Python/JavaScript SAST、生产 Docker 镜像 Trivy HIGH/CRITICAL 扫描全部通过；
- [ ] 当前生产候选镜像存在可追踪 CycloneDX SBOM；
- [ ] `security/waivers.json` 不存在过期 waiver；任何 Critical/High/ERROR 例外均有 finding ID、scope、owner、reason 和明确到期日；
- [ ] 依赖、镜像和仓库密钥扫描无未接受的 Critical/High 风险。

## B. 基础设施

- [ ] dev、staging、production 的域名、数据库、对象存储和密钥完全隔离；
- [ ] 正式域名、DNS、ICP备案等适用手续和 TLS 已完成；
- [ ] PostgreSQL 16 仅内网访问，磁盘、连接数和慢查询有监控；
- [ ] 腾讯云 COS 上海地域私有 Bucket 启用加密、版本、生命周期和访问审计；
- [ ] Nginx 80→443、安全响应头、25MB 上传限制和限流生效；
- [ ] API、Scheduler、Nginx 使用最小权限、只读根文件系统和日志轮转；
- [ ] 主机、容器和数据库完成 NTP 校时。

## C. 生产配置

- [ ] `python scripts/validate_production_env.py --env-file .env` 返回 valid；
- [ ] `python scripts/verify_production.py --env-file .env --require-certificates --require-image-digest --require-image-inspect --scan-subject scan-subject.json` 返回 valid，且回拉镜像 ImageID/Descriptor 属于 Security gate 已验证身份集合；
- [ ] `python scripts/preflight_v12.py --env-file .env --require-certificates --compose-database --scan-subject scan-subject.json --output dist/v12-preflight.json` 返回 valid；
- [ ] 标准 Docker 部署的数据库 revision 和 V1.2 reconciliation 均在 Compose 网络内执行，未回退到本地 SQLite；
- [ ] API/Scheduler 使用 `docker/prepare-env.sh` URL 编码后的 `DATABASE_URL`，特殊字符凭据已验证；
- [ ] `JWT_SECRET`、`FIELD_ENCRYPTION_KEY`、`PHONE_HASH_SECRET`、`PHONE_FINGERPRINT_SECRET` 独立且已托管；
- [ ] `PHONE_FINGERPRINT_SECRET` 与 `PHONE_HASH_SECRET` 不相同；
- [ ] `AUTO_CREATE_SCHEMA=false`、`SEED_DEMO=false`、`RUN_DB_MIGRATIONS=false`；
- [ ] `WECHAT_DEV_MOCK=false`、`FEISHU_DEV_MOCK=false`；
- [ ] `CORS_ORIGINS`、`TRUSTED_HOSTS` 仅包含正式域名；
- [ ] 飞书启用状态与凭据一致；启用时锁定“客户视图”且 `FEISHU_WRITEBACK_ENABLED=false`，不配置定时同步；不启用时 `FEISHU_ENABLED=false`；
- [ ] 正式环境没有演示账号、演示数据和默认密码。

## D. 数据迁移和对账

- [ ] PostgreSQL V1.0.1 备份副本升级到 V1.2 的预演通过；
- [ ] PostgreSQL 验证确认有效派发部分唯一索引、积分幂等、退回唯一和供应奖励唯一约束实际存在；
- [ ] 记录迁移耗时、锁等待、磁盘增长和停止条件；
- [ ] 上线窗口完成即时数据库和对象存储备份；
- [ ] `migrate_v12_data.py --dry-run` 无失败行；
- [ ] 正式手机号指纹回填完成，检查点状态为 `COMPLETED`；
- [ ] 固定 RBAC 差异预览已人工复核，应用后 `v12-rbac-after.json` 为 `result.changed=false`；
- [ ] 有权限变化时存在 `SYSTEM_RBAC_SYNC` 审计，新增和移除映射与批准的代码矩阵一致；
- [ ] 生产 API 在未同步 RBAC 差异时拒绝启动，不存在启动时静默回收权限；
- [ ] `reconcile_v12.py` 返回 valid；
- [ ] `scripts/check_binding_integrity.py` 返回 valid，且证据归档到上线包或 `dist/`；
- [ ] `dist/v101-baseline-before.json`、RBAC 预览/应用/复查 JSON、`dist/v12-reconciliation-before-backfill.json`、`dist/v12-reconciliation-after.json` 和 `dist/v12-preflight.json` 已持久化到宿主机并归档；
- [ ] 所有 JSON 证据通过 `python -m json.tool` 校验，未保存在 `run --rm` 容器临时目录；
- [ ] 无未知历史状态、重复有效派发单或积分余额差异；
- [ ] 奖励结算/冲正流水的公司、类型、业务 ID、金额和关联原流水与奖励事实一致；
- [ ] APPROVED 退回返分流水及其关联原 CLAIM 流水与公司、assignment、return 和金额事实一致；
- [ ] 截图、录音的 `object_key`、64 位 SHA-256 与实际对象抽查一致。

## E. 真实外部联调

- [ ] 企业主体服务号已认证；
- [ ] 网页授权域名、OAuth 回调、Cookie 会话在 iOS/Android 微信通过；
- [ ] 派发、领取、申诉、核验、奖励等微信通知和失败重试通过；
- [ ] 跨公司转发深链返回无权，失效深链不展示客资摘要；
- [ ] 飞书启用时，增量同步、幂等、异常记录和状态回写通过；
- [ ] 对象文件只能通过授权访问，永久公网 URL 不存在。

## F. 业务和安全验收

- [ ] 平台运营、财务、电销、审核员和加盟商全流程 E2E 通过；
- [ ] 并发派发、并发领取、重复返分和奖励结算验证通过；
- [ ] 越权读取手机号、积分、财务字段和证据文件均失败；
- [ ] 实际节假日工作日历已按 `V1.2_WORKDAY_CALENDAR.md` 导入，重复导入幂等，并完成管理员写入/运营只读/无权限 403 验收；
- [ ] 奖励比例、上下限、去重窗口、价格和服务区域完成审批；
- [ ] 服务协议、隐私政策、客户授权和数据保留策略完成法务确认；
- [ ] 3–5 家试点加盟商完成 UAT；
- [ ] 各角色 SOP、培训和问题反馈渠道就绪。

## G. 运维和回滚

- [ ] API 请求量、P95、5xx、数据库连接、CPU、内存和磁盘有监控；
- [ ] Outbox DEAD、Scheduler 停摆、奖励积压、备份失败和证书到期有告警；
- [ ] PostgreSQL 每日备份和对象存储版本策略已自动执行；
- [ ] 数据库、对象、密钥和应用的联合恢复演练通过；
- [ ] 上一版本不可变镜像、上线前备份和回滚命令已复核；
- [ ] 上线值班表、P0/P1 响应时限和升级联系人已发布。

## H. 灰度和全量

- [ ] 上线冒烟全绿，积分和业务对账差异为 0；
- [ ] 第一批仅开放 3–5 家加盟商；
- [ ] 灰度 24–72 小时无 P0/P1 缺陷；
- [ ] 每日检查 5xx、Outbox、奖励积压、积分和用户反馈；
- [ ] 产品、业务、财务和技术完成全量开放签字；
- [ ] 24 小时、72 小时和 7 天复盘安排已确定。
