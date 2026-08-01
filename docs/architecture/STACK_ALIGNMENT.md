# 技术栈对齐说明

## 1. 目标与本交付实现

| 层 | PRD/总体文档目标 | 本代码包实现 | 迁移边界 |
|---|---|---|---|
| 加盟商端 | Vue 3 + TypeScript + Vite | 响应式 HTML/CSS/ES Module SPA | API 与路由不变，可逐页替换为 Vue SFC |
| 电销端 | Vue 3 + TypeScript + Vite | 响应式 HTML/CSS/ES Module SPA | 同上 |
| 管理后台 | Vue 3 + TypeScript + Vite | 响应式 HTML/CSS/ES Module SPA | 同上 |
| 后端 | NestJS + TypeScript | FastAPI + SQLAlchemy 模块化单体 | Controller/Service/Repository/DTO 一一映射 |
| 数据库 | PostgreSQL | PostgreSQL 为生产目标，SQLite 为本地零依赖模式 | SQLAlchemy 模型与迁移支持 PostgreSQL |
| 对象存储 | COS/OSS 私有桶 | 本地私有目录 + S3 兼容适配器 | 配置切换，无业务代码改动 |

## 2. 为什么保留此实现

本代码包优先交付“可运行、可测试、可审计”的完整 P0 业务闭环。领域状态、数据库约束、事务边界、错误码、权限投影和 API 合同均按 PRD 编写，因此后续替换框架不改变业务设计。

## 3. NestJS 模块映射

| Python 模块 | NestJS 目标模块 |
|---|---|
| `auth` | `AuthModule` |
| `companies` | `CompanyModule` |
| `leads` / `feishu` | `LeadModule` / `FeishuSyncModule` |
| `verification` | `VerificationModule` |
| `dispatch` | `DispatchModule` |
| `points` | `PointsModule` |
| `followups` | `FollowupModule` |
| `returns` | `ReturnModule` |
| `notifications` | `NotificationModule` |
| `audit` | `AuditModule` |
