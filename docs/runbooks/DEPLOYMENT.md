# 合家美宅客资平台 V1.2 生产部署手册

> 本手册分别记录 `代码完成`、`自动化通过` 与 `真实环境验收`。代码或自动门禁通过只允许进入目标环境验证，不能直接标记生产上线。

## 1. 适用范围

本手册用于将已评审的 V1.2 镜像部署到生产环境。真实服务号联调、业务 UAT 和灰度批准必须另行完成，代码通过不等于业务可以全量开放。

## 2. 生产拓扑

- Nginx：80 强制跳转 HTTPS，443 终止 TLS，配置安全响应头、限流和 25MB 上传限制；
- API：FastAPI，托管加盟商 H5、内部电销 H5、管理后台和业务接口；
- Scheduler：处理通知 Outbox、领取/跟进任务、低积分提醒和每小时供应奖励结算；
- PostgreSQL 16：唯一生产主库；
- 私有 S3/COS/OSS：保存聊天截图和电话录音；
- 日志与告警平台：采集 API、Scheduler、Nginx、数据库和备份任务；
- 异地备份：保存 PostgreSQL 自定义格式备份及对象存储版本。

## 3. 生产前提

1. `release/v1.2.0` 最新 CI 全绿，PR 无 Critical/High/P1/P2 未解决项；
2. `APP_IMAGE` 使用 `仓库:APP_VERSION@sha256:digest` 形式，例如 `registry.example.com/zhongshu-lead-platform:1.2.0@sha256:...`；
3. 镜像 OCI `org.opencontainers.image.version` 与 `APP_VERSION` 完全一致；
4. 正式域名、TLS、服务号授权域名和 OAuth 回调已配置；
5. PostgreSQL、对象存储、日志、告警和备份已验收；
6. `PHONE_HASH_SECRET` 与 `PHONE_FINGERPRINT_SECRET` 分离并妥善托管；
7. 演示账号、`SEED_DEMO`、微信/飞书模拟开关全部关闭；
8. 已完成 `V1.2_MIGRATION_RUNBOOK.md` 的预演和 `V1.2_ROLLBACK.md` 的恢复演练。

## 4. 配置校验

```bash
cp .env.docker.example .env
mkdir -p infra/certs backups dist
# 放置 fullchain.pem、privkey.pem，并填写 .env 的真实配置
python scripts/validate_production_env.py --env-file .env
python scripts/verify_production.py --env-file .env --require-certificates
```

上述宿主机检查会在 `.env` 未显式提供 `DATABASE_URL` 时，按 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 生成 URL 编码后的 Compose 内部 PostgreSQL URL，仅用于配置一致性验证。API 与 Scheduler 容器启动时由 `docker/prepare-env.sh` 使用同一 URL 编码规则生成 `DATABASE_URL`，因此密码、用户名或数据库名包含 `/`、`#`、`@`、空格等保留字符时不会出现宿主机校验与容器实际连接语义不一致。

`TRUST_PROXY_HEADERS` 必须在 `.env` 中显式声明为 `true`：本拓扑的 nginx 始终强制覆写 `x-real-ip`（`infra/nginx/production.conf.template`），API 信任该头后限流键与审计 IP 才能反映真实客户端地址；若缺失或设为 `false`，`validate_production_env.py` 会直接拒绝。生产校验一律要求 `true`；若确实要把 API 改为无反代直连部署，必须同步调整 `validate_production_settings` 的该校验，不允许仅改配置绕过。

真正的数据库 revision 和业务对账必须在 Compose 网络内执行。

飞书为显式可选能力：

- 启用：`FEISHU_ENABLED=true`，并配置 App、Token、Table 和字段映射；
- 不启用：`FEISHU_ENABLED=false`，不保留无效凭据；
- 无论是否启用，生产均要求 `FEISHU_DEV_MOCK=false`。

## 5. 拉取不可变镜像并启动数据库

在 `.env` 中将 `APP_IMAGE` 设置为已评审的版本 tag + sha256 digest，然后执行：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml pull
python scripts/verify_production.py \
  --env-file .env \
  --require-certificates \
  --require-image-digest \
  --require-image-inspect \
  --scan-subject scan-subject.json
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d db
```

`verify_production.py` 直接从 `.env` 读取 `APP_IMAGE` 与 `APP_VERSION`，不会依赖宿主 shell 已导出同名变量；它会检查显式版本 tag、sha256 digest、实际拉取镜像的 OCI 版本标签，并要求 Docker ImageID 与 Security Analysis 产出的 `scan-subject.json` 完全一致。生产覆盖配置将 API 的 `RUN_DB_MIGRATIONS` 固定为 `false`，避免应用启动时隐式迁移或多个实例竞争执行迁移。

## 6. 备份、迁移和回填

首先进入维护窗口并停止业务写入：

```bash
ENV_FILE=.env BACKUP_RETENTION_DAYS=30 sh scripts/backup_postgres.sh
```

显式执行 Alembic：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm -T -e RUN_DB_MIGRATIONS=true api true
```

在启动 API 前先预览固定 RBAC 差异，人工复核所有将被回收的权限，再显式应用并复查已精确收敛：

```bash
mkdir -p dist
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm -T -e RUN_DB_MIGRATIONS=false api \
  python scripts/sync_rbac.py \
  > dist/v12-rbac-preview.json

docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm -T -e RUN_DB_MIGRATIONS=false api \
  python scripts/sync_rbac.py --apply --source release_v1.2.0 \
  > dist/v12-rbac-apply.json

docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm -T -e RUN_DB_MIGRATIONS=false api \
  python scripts/sync_rbac.py \
  > dist/v12-rbac-after.json
```

`v12-rbac-after.json` 必须为 `result.changed=false`。有实际变更时必须存在 `SYSTEM_RBAC_SYNC` 审计；完整操作与回滚步骤见 `V1.2_RBAC_SYNC.md`。
生产 API 启动还会执行只读门禁；若发现未同步差异将直接拒绝启动，不会绕过人工复核自动回收权限。

先只读预检，再执行历史手机号指纹回填：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm -T -e RUN_DB_MIGRATIONS=false api \
  python scripts/migrate_v12_data.py --dry-run --batch-size 500 --max-batches 10000 --fail-on-row-error

docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm -T -e RUN_DB_MIGRATIONS=false api \
  python scripts/migrate_v12_data.py --batch-size 500 --max-batches 10000 --fail-on-row-error
```

执行数据对账，并将 JSON 证据写入宿主机 `dist/`，禁止写入 `run --rm` 容器内的临时路径：

```bash
mkdir -p dist
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm -T -e RUN_DB_MIGRATIONS=false api \
  python scripts/reconcile_v12.py \
  > dist/v12-reconciliation.json
python -m json.tool dist/v12-reconciliation.json >/dev/null
```

出现失败行、未知历史状态、重复有效派发单、积分差异、奖励/返分流水语义不一致或证据元数据异常时，判定为 `NO-GO`。

## 7. 启动应用与最终 Preflight

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d api
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d scheduler nginx
```

检查：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml ps
curl -fsS https://app.example.com/health/live
curl -fsS https://app.example.com/health/ready
python scripts/preflight_v12.py \
  --env-file .env \
  --require-certificates \
  --compose-database \
  --storage-canary \
  --scan-subject scan-subject.json \
  --output dist/v12-preflight.json
```

`--compose-database` 是 Docker 生产部署的强制参数。它同时执行以下强门禁：

- `APP_IMAGE` 的显式版本 tag 必须与 `APP_VERSION` 完全一致；
- `APP_IMAGE` 必须包含 `@sha256:` digest；
- 本机实际拉取镜像的 OCI `org.opencontainers.image.version` 必须与 `APP_VERSION` 一致；
- 本机实际拉取镜像的 Docker ImageID 必须与 `scan-subject.json` 中 Security Analysis 候选镜像完全一致；
- Alembic revision 与 V1.2 数据对账必须通过一次性 API 容器在真实 `db:5432` Compose 网络内执行；
- 没有显式可达 `DATABASE_URL` 且未使用 Compose 模式时直接失败，禁止误读本地 SQLite。

## 8. 上线冒烟

必须按真实角色验证：

1. 微信 OAuth 登录和公司绑定；
2. 平台手工录入和供应商上传；
3. 供应商资料初审；
4. 候选公司和人工派发；
5. 加盟商领取、单次扣分和手机号解锁；
6. 截图或录音退回申诉、后置电销核验和终审返分；
7. 奖励观察、冻结、结算和异常冲正；
8. 微信通知和深链；
9. V1.2 报表、审计和业务 ID 追踪；
10. 全公司积分与流水对账。

## 9. 灰度策略

- 第一批仅开放 3–5 家已完成培训的加盟商；
- 连续观察 24–72 小时；
- 每日核对 5xx、Outbox DEAD、奖励积压、积分差异和用户反馈；
- 无 P0/P1 缺陷并由产品、业务、财务、技术共同签字后逐批扩大；
- 禁止首次直接向全部加盟商开放。

## 10. 回滚

- 应用回滚：将 `APP_IMAGE` 切换为上一已验证的 `版本tag@sha256:digest` 后重新启动；
- 数据库：优先恢复上线前备份，不得未经评审盲目 downgrade；
- 私有对象：使用对象存储版本或供应商恢复能力；
- 账务异常：立即停止领取、结算和返分入口，保留不可变流水与审计证据。

详细触发条件和命令见 `docs/runbooks/V1.2_ROLLBACK.md`。未完成备份与恢复演练时禁止正式上线。
