# V1.2 生产上线检查表

所有 P0 项必须有证据并由责任人签字。任何一项失败均为 `NO-GO`。

## A. 版本和质量

- [ ] 上线提交来自 `release/v1.2.0`，对应受保护的 V1.2 tag；
- [ ] PR 与 Release CI 的全量测试、PostgreSQL 迁移和 Chromium 浏览器任务全部通过；
- [ ] PR 无未解决的 Critical/High/P1/P2 评审问题；
- [ ] `APP_VERSION=1.2.x`，Dockerfile 默认 `APP_VERSION=1.2.0`，`APP_IMAGE` 指向已评审镜像，正式窗口使用 digest；
- [ ] README、部署、迁移、回滚、UAT 和发布说明均为 V1.2；
- [ ] 依赖、镜像和仓库密钥扫描无未接受的 Critical/High 风险。

## B. 基础设施

- [ ] dev、staging、production 的域名、数据库、对象存储和密钥完全隔离；
- [ ] 正式域名、DNS、ICP备案等适用手续和 TLS 已完成；
- [ ] PostgreSQL 16 仅内网访问，磁盘、连接数和慢查询有监控；
- [ ] 私有 S3/COS/OSS 启用加密、版本、生命周期和访问审计；
- [ ] Nginx 80→443、安全响应头、25MB 上传限制和限流生效；
- [ ] API、Scheduler、Nginx 使用最小权限、只读根文件系统和日志轮转；
- [ ] 主机、容器和数据库完成 NTP 校时。

## C. 生产配置

- [ ] `python scripts/validate_production_env.py --env-file .env` 返回 valid；
- [ ] `python scripts/verify_production.py --env-file .env --require-certificates` 返回 valid；
- [ ] `python scripts/preflight_v12.py --env-file .env --require-certificates --compose-database --output dist/v12-preflight.json` 返回 valid；
- [ ] 标准 Docker 部署的数据库 revision 和 V1.2 reconciliation 均在 Compose 网络内执行，未回退到本地 SQLite；
- [ ] `JWT_SECRET`、`FIELD_ENCRYPTION_KEY`、`PHONE_HASH_SECRET`、`PHONE_FINGERPRINT_SECRET` 独立且已托管；
- [ ] `PHONE_FINGERPRINT_SECRET` 与 `PHONE_HASH_SECRET` 不相同；
- [ ] `AUTO_CREATE_SCHEMA=false`、`SEED_DEMO=false`、`RUN_DB_MIGRATIONS=false`；
- [ ] `WECHAT_DEV_MOCK=false`、`FEISHU_DEV_MOCK=false`；
- [ ] `CORS_ORIGINS`、`TRUSTED_HOSTS` 仅包含正式域名；
- [ ] 飞书启用状态与凭据一致；不启用时 `FEISHU_ENABLED=false`；
- [ ] 正式环境没有演示账号、演示数据和默认密码。

## D. 数据迁移和对账

- [ ] PostgreSQL V1.0.1 备份副本升级到 V1.2 的预演通过；
- [ ] 记录迁移耗时、锁等待、磁盘增长和停止条件；
- [ ] 上线窗口完成即时数据库和对象存储备份；
- [ ] `migrate_v12_data.py --dry-run` 无失败行；
- [ ] 正式手机号指纹回填完成，检查点状态为 `COMPLETED`；
- [ ] `reconcile_v12.py` 返回 valid；
- [ ] `dist/v101-baseline-before.json`、`dist/v12-reconciliation-before-backfill.json`、`dist/v12-reconciliation-after.json` 和 `dist/v12-preflight.json` 已持久化到宿主机并归档；
- [ ] 所有 JSON 证据通过 `python -m json.tool` 校验，未保存在 `run --rm` 容器临时目录；
- [ ] 无未知历史状态、重复有效派发单、积分差异或缺失奖励/返分流水；
- [ ] 截图、录音的 `object_key`、SHA-256 与实际对象抽查一致。

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
- [ ] 实际节假日工作日历已导入并验收；
- [ ] 奖励比例、上下限、去重窗口、价格和服务区域完成审批；
- [ ] 服务协议、隐私政策、客户授权和数据保留策略完成法务确认；
- [ ] 3–5 家试点加盟商完成 UAT；
- [ ] 各角色 SOP、培训和问题反馈渠道就绪。

## G. 运维和回滚

- [ ] API 请求量、P95、5xx、数据库连接、CPU、内存和磁盘有监控；
- [ ] Outbox DEAD、Scheduler 停摆、奖励积压、备份失败和证书到期有告警；
- [ ] PostgreSQL 每日备份和对象存储版本策略已自动执行；
- [ ] 数据库、对象、密钥和应用的联合恢复演练通过；
- [ ] 上一版本镜像、上线前备份和回滚命令已复核；
- [ ] 上线值班表、P0/P1 响应时限和升级联系人已发布。

## H. 灰度和全量

- [ ] 上线冒烟全绿，积分和业务对账差异为 0；
- [ ] 第一批仅开放 3–5 家加盟商；
- [ ] 灰度 24–72 小时无 P0/P1 缺陷；
- [ ] 每日检查 5xx、Outbox、奖励积压、积分和用户反馈；
- [ ] 产品、业务、财务和技术完成全量开放签字；
- [ ] 24 小时、72 小时和 7 天复盘安排已确定。
