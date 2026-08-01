# 众墅之家客资审核、派发与积分管理平台

本仓库是 PRD V1.0 执行版对应的 P0 可运行代码基线，覆盖：

- 飞书客资导入、暂存、幂等与疑似重复；
- 内部电销核验与一键拨号；
- 合格客资池与运营人工派发；
- 加盟商微信 H5 领取、扣积分、跟进、退回举证；
- 线下收款后的人工充值积分与不可变流水；
- 管理员退回审核、审核返积分与审计；
- 角色权限、字段投影、站内通知、Outbox、配置中心；
- Docker Compose、数据库迁移、测试、运行手册和代码评审记录。

## 技术实现说明

PRD 的目标架构为 Vue 3 + NestJS + PostgreSQL。本交付包在隔离构建环境中采用 **FastAPI + SQLAlchemy + PostgreSQL/SQLite + 依赖最小化的响应式 Web 前端**，完整保持领域模型、API、事务边界、权限和部署契约。`docs/architecture/STACK_ALIGNMENT.md` 给出与目标 NestJS/Vue 架构的逐模块映射，后续可无损迁移前端构建层和服务框架。

## 快速启动

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

演示账号见 `docs/runbooks/DEMO_ACCOUNTS.md`。

## 代码评审与提交纪律

每个交付任务均执行：

1. 实现与自测；
2. 运行 `python scripts/task_review.py --task <ID> --title <标题>`；
3. 检查生成的 `docs/reviews/<ID>.md`；
4. 将实现、测试和评审记录一起提交；
5. Git 提交信息引用 PRD 需求 ID。

完整提交记录可通过 `git log --oneline --decorate` 查看。

## 发布打包

所有小任务完成评审并提交后，可生成干净源码包、完整 Git 历史和总交付包：

```bash
python scripts/package_release.py --version V1.0.0-P0 --output-dir /mnt/data
```

打包规则、恢复方法和 SHA256 校验见 `docs/runbooks/RELEASE_PACKAGING.md`。
