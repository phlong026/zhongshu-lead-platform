# V1.0.1 生产部署手册

## 1. 生产拓扑

- Nginx：80 端口强制跳转 HTTPS，443 终止 TLS，并配置请求限流、安全响应头和 25MB 上传限制；
- API：FastAPI 单体应用，托管加盟商 H5、电销 H5、管理后台和业务接口；
- Scheduler：处理微信通知 Outbox、24/48 小时任务、跟进逾期与低积分提醒；
- PostgreSQL：唯一业务主库；
- 私有对象存储：聊天截图、电话录音和回单，生产优先使用 S3/COS/OSS 私有桶；
- 备份目录或异地备份桶：保存数据库与本地私有文件备份。

## 2. 生产前准备

```bash
cp .env.docker.example .env
# 填写真实域名、随机密钥、数据库口令、微信、飞书和对象存储配置
mkdir -p infra/certs backups
# 放置证书：infra/certs/fullchain.pem 和 infra/certs/privkey.pem
python scripts/validate_production_env.py --env-file .env
python scripts/verify_production.py --env-file .env --require-certificates
```

生产必须满足：

- `APP_ENV=production`；
- `APP_BASE_URL` 和微信 OAuth 回调使用同一个 HTTPS 域名；
- `WECHAT_DEV_MOCK=false`、`FEISHU_DEV_MOCK=false`；
- 不使用示例密钥、示例数据库口令和演示数据；
- `AUTO_CREATE_SCHEMA=false`，数据库结构仅通过 Alembic 管理；
- `TRUSTED_HOSTS`、`CORS_ORIGINS` 使用明确生产域名；
- 微信、飞书和对象存储凭据通过环境变量注入，不提交 Git。

## 3. 构建与启动

```bash
docker compose \
  --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  build --pull api scheduler
docker compose \
  --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d
```

检查：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml ps
curl -fsS https://app.example.com/health/live
curl -fsS https://app.example.com/health/ready
```

## 4. 发布顺序

1. 执行数据库和对象存储备份；
2. 运行生产配置校验；
3. 构建带版本号的应用镜像；
4. API 启动脚本执行 `alembic upgrade head`；
5. API 健康后 Scheduler 才启动；
6. 检查微信 OAuth、飞书同步、人工派发、领取扣分、退回审核和积分对账；
7. 灰度 3～5 家加盟商后再全量开放。

## 5. 回滚

- 应用回滚：切换 `APP_IMAGE` 到上一镜像版本后重新 `up -d`；
- 数据库迁移：只有经过评审且确认可逆时执行 Alembic downgrade；
- 业务数据：使用 `scripts/restore_postgres.sh`，恢复前必须进入维护窗口；
- 私有文件：本地存储使用 `scripts/restore_private_storage.sh`，云对象存储使用版本控制或供应商恢复功能。

生产不得在未备份时直接回滚数据库。
