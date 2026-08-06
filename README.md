# 众墅之家客资审核、派发与积分管理平台 V1.2

V1.2 是客资供给、审核、人工派发、加盟商领取、退回申诉、供应奖励、通知、报表与审计的一体化生产候选版本。

## 已冻结的业务边界

- 平台手工客资校验和去重通过后直接进入 `READY_DISPATCH`；
- 供应商客资需具备有效供给能力并通过平台资料初审；
- 正常客资不做前置电销，只有退回申诉创建 `RETURN_VERIFY`；
- 退回证据为聊天截图或电话录音至少一项；
- 申诉期与供应奖励观察期统一为 3 个工作日；
- V1.2 仅支持平台人工派发，不提供自动、随机、轮询、权重或抢单；
- 禁止供应商将自己提供的客资派发给自己；
- 奖励仅在观察期结束且不存在有效申诉时结算，异常冲正单独审计。

V1.2 不包含在线支付、自动派发、微信小程序、云外呼或 H5 自动录音。

## 技术实现

- FastAPI、SQLAlchemy 2、Alembic；
- PostgreSQL 16 生产主库，SQLite 仅用于本地开发和部分单元测试；
- 加盟商微信 H5、内部电销 H5、平台管理后台；
- API 与 Scheduler 分进程运行；
- 私有 S3/COS/OSS 保存截图和录音；
- Nginx、HTTPS、RBAC、字段隔离、结构化日志、备份恢复和审计追踪。

## 本地开发

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/init_db.py
python scripts/seed_demo.py
uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload
```

访问入口：

- 加盟商 H5：`http://localhost:8000/h5/`
- V1.2 加盟商工作台：`http://localhost:8000/h5/v12-workbench.html`
- 内部电销 H5：`http://localhost:8000/call/`
- 管理后台：`http://localhost:8000/admin/`
- V1.2 运营台：`http://localhost:8000/admin/v12-operations.html`
- OpenAPI：`http://localhost:8000/docs`

演示账号只允许用于开发和自动验收，见 `docs/runbooks/DEMO_ACCOUNTS.md`。

## 自动质量门禁

面向 `release/v1.2.0` 的 PR 和发布分支执行：

1. 全量 Python 测试、JavaScript 检查、密钥扫描、编译和空白检查；
2. SQLite V1.0.1 → V1.2 升降级循环；
3. PostgreSQL 16 历史夹具升级、手机号指纹回填、数据对账和再升级；
4. Chromium 桌面管理后台与移动 H5 的真实浏览器交互和截图检查。

## T30 历史数据迁移

生产写入冻结并完成备份后执行：

```bash
python scripts/migrate_v12_data.py --dry-run --batch-size 500 --max-batches 10000 --fail-on-row-error
python scripts/migrate_v12_data.py --batch-size 500 --max-batches 10000 --fail-on-row-error
python scripts/reconcile_v12.py --output dist/v12-reconciliation.json
```

迁移任务使用 `v12_migration_checkpoints` 断点续跑；检查点和错误样本只保存业务 ID 与错误码，不保存明文手机号。

## 生产部署

```bash
cp .env.docker.example .env
# 填写正式域名、独立随机密钥、微信、PostgreSQL、对象存储和不可变 APP_IMAGE
python scripts/validate_production_env.py --env-file .env
python scripts/verify_production.py --env-file .env --require-certificates
python scripts/preflight_v12.py --env-file .env --require-certificates
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d
```

飞书是显式可选集成：启用时设置 `FEISHU_ENABLED=true` 并配置全部凭据；不启用时不得保留无效生产凭据。

生产操作文档：

- `docs/runbooks/DEPLOYMENT.md`
- `docs/runbooks/PRODUCTION_CHECKLIST_V1.2.md`
- `docs/runbooks/V1.2_MIGRATION_RUNBOOK.md`
- `docs/runbooks/V1.2_UAT.md`
- `docs/runbooks/V1.2_GO_NO_GO.md`
- `docs/runbooks/V1.2_ROLLBACK.md`
- `docs/runbooks/V1.2_POST_LAUNCH.md`
- `docs/runbooks/BACKUP_RESTORE.md`
- `docs/runbooks/WECHAT_GATE0.md`

真实服务号联调、真实加盟商 UAT、生产备份恢复演练和灰度开放必须在目标环境执行，不能由代码测试替代。

## 发布打包

```bash
python scripts/package_release.py --version V1.2.0 --output-dir dist/release
```

源码包只包含 Git 已跟踪文件；`.env`、数据库、证据文件、备份和真实密钥不会进入交付包。
