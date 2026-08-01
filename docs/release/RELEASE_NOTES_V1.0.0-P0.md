# 众墅之家客资平台 v1.0.0-p0 发布说明

## 版本定位

这是面向内部试运行和灰度验收的 P0/MVP 代码基线，不是未经联调即可直接面向全部加盟商开放的最终生产版本。

## 本版本已交付

- 响应式加盟商微信 H5；
- 内部电销 H5；
- 角色化 Web 管理后台；
- FastAPI 模块化单体后端与 OpenAPI；
- PostgreSQL/SQLite 数据访问、Alembic 迁移；
- 飞书导入适配器和开发模拟器；
- 微信 OAuth/消息适配器和开发模拟器；
- 单积分账户、线下人工充值、不可变流水；
- 人工派发、领取扣分、跟进、退回举证、审核返分；
- RBAC、字段投影、手机号加密、审计日志、Outbox；
- Docker Compose、Nginx、调度器、备份恢复与运维手册；
- 任务级代码评审记录和自动化测试。

## 技术实现与目标架构

PRD 目标技术栈为 Vue 3 + NestJS + PostgreSQL。本隔离构建环境采用 FastAPI + SQLAlchemy + 依赖最小化静态 ES Module SPA，保留相同的领域边界、API 契约、权限规则和事务语义。映射说明见 `docs/architecture/STACK_ALIGNMENT.md`。

## 升级与部署

本地验证：

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/init_db.py
python scripts/seed_demo.py
uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000
```

生产建议使用 Docker Compose + PostgreSQL + 私有对象存储，具体见 `docs/runbooks/DEPLOYMENT.md`。

## 已知边界

1. 真实微信公众号能力必须完成 Gate 0，通知类型取决于企业主体和后台实际权限；
2. 飞书字段名、表格权限和状态回写必须与客户实际多维表格联调；
3. H5 不能自动录制手机原生通话，只能上传用户已有录音；
4. P0 只做人工派发，自动轮询属于 P1；
5. P0 不接任何在线支付；
6. 生产发布前需完成目标云环境、安全和隐私合规验收。
