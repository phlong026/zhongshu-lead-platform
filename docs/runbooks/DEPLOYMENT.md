# 部署手册

## 1. 最小生产拓扑

- Nginx：HTTPS 终止和反向代理；
- API：FastAPI 单体应用，同时托管加盟商 H5、电销 H5 和管理后台静态文件；
- Scheduler：处理通知 Outbox、24/48 小时提醒与跟进逾期；
- PostgreSQL：唯一业务主库；
- 私有对象存储：聊天截图、电话录音，开发环境可使用私有本地卷，生产建议切换 S3/COS/OSS 兼容私有桶。

## 2. 首次部署

```bash
cp .env.docker.example .env
# 编辑全部密钥、域名、微信和飞书配置
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8080/health/ready
```

生产环境不得设置 `SEED_DEMO=true`，不得使用示例密码或默认数据库口令。

## 3. HTTPS 与域名

将企业域名解析到服务器，在外层负载均衡或 Nginx 配置正式证书。`APP_BASE_URL`、微信网页授权域名、OAuth 回调地址和飞书回调地址必须保持一致。

## 4. 升级与回滚

```bash
git pull
docker compose build api scheduler
docker compose run --rm api alembic upgrade head
docker compose up -d api scheduler
```

升级前先备份数据库和对象存储。应用静态资源随镜像版本发布；回滚时恢复上一镜像标签，数据库迁移仅在确认可逆时执行 downgrade。
