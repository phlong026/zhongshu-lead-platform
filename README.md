# 众墅之家客资审核、派发与积分管理平台 V1.0.1

本仓库对应《PRD V1.0·执行版》的 V1.0.1 生产候选版本，覆盖：

- 真实微信公众号 OAuth、加盟商公司绑定和安全客资深链接；
- 微信通知 Outbox、失败重试、充值到账与低积分提醒；
- 飞书多维表格增量同步、幂等、异常记录和状态回写；
- 内部电销核验、一键拨号、合格客资池和运营人工派发；
- 加盟商微信 H5 领取、扣积分、跟进和双证据退回申请；
- 单一积分账户、充值档位、V1/V2/V3 权益、价格规则、冲正和对账；
- 角色化经营漏斗、区域表现及老板/财务积分报表；
- 管理员退回审核、审核返积分、RBAC、字段隔离和审计；
- HTTPS/Nginx、生产配置校验、结构化日志、健康检查、备份恢复和发布打包。

V1.0.1 明确不包含自动派发、轮询/权重派发、在线支付、微信小程序、云外呼和自动通话录音。

## 技术实现

当前实现采用 **FastAPI + SQLAlchemy + PostgreSQL/SQLite + 依赖最小化的响应式 Web 前端**。`docs/architecture/STACK_ALIGNMENT.md` 给出与 Vue 3 + NestJS 目标架构的模块映射。生产主库使用 PostgreSQL，聊天截图、电话录音和回单使用私有对象存储。

## 本地启动

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/init_db.py
python scripts/seed_demo.py
uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload
```

访问：

- 加盟商 H5：`http://localhost:8000/h5/`
- 内部电销 H5：`http://localhost:8000/call/`
- 管理后台：`http://localhost:8000/admin/`
- OpenAPI：`http://localhost:8000/docs`

演示账号仅限开发环境，见 `docs/runbooks/DEMO_ACCOUNTS.md`。

## 生产部署

```bash
cp .env.docker.example .env
# 填写真实域名、随机密钥、微信、飞书、PostgreSQL 和对象存储配置
python scripts/validate_production_env.py --env-file .env
python scripts/verify_production.py --env-file .env --require-certificates
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

详细说明见：

- `docs/runbooks/DEPLOYMENT.md`
- `docs/runbooks/PRODUCTION_CHECKLIST_V1.0.1.md`
- `docs/runbooks/BACKUP_RESTORE.md`
- `docs/runbooks/WECHAT_GATE0.md`
- `docs/runbooks/FEISHU_MAPPING.md`

## 代码评审流程

每个小功能执行：实现与自测 → 自动检查 → Diff 检查 → 代码评审 → PR → 合并。评审记录位于 `docs/reviews/`，完整历史可通过 Git 查看。

## V1.0.1 发布打包

```bash
python scripts/package_release.py --version V1.0.1 --output-dir /mnt/data
```

输出包括完整源码 ZIP、完整 Git Bundle、总交付包和 SHA-256 校验文件。真实密钥、`.env`、数据库、证据文件和备份不会进入源码包。
