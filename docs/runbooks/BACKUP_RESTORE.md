# V1.2 备份与恢复

## 1. 目标

- 上线前必须存在可验证的 PostgreSQL、对象存储和配置备份；
- 生产建议 RPO 不高于 24 小时，发布窗口使用即时备份；
- RTO 以隔离环境恢复演练实测值为准，不得只填写理论值；
- 数据库恢复、对象恢复、密钥恢复和应用镜像回滚必须作为一个整体演练。

## 2. PostgreSQL 自动备份

```bash
ENV_FILE=.env BACKUP_RETENTION_DAYS=30 sh scripts/backup_postgres.sh
```

脚本生成 PostgreSQL 自定义格式备份与 SHA-256 校验文件，并清理超过保留期的旧文件。生产需要：

- 每日自动执行；
- 备份失败告警；
- 备份文件服务端加密；
- 至少一份异地副本；
- 备份账号只具备完成备份所需权限；
- 发布前即时备份不得被日常保留任务提前删除。

恢复必须明确确认：

```bash
CONFIRM_RESTORE=YES ENV_FILE=.env \
  sh scripts/restore_postgres.sh backups/postgres/zhongshu-YYYYMMDDTHHMMSSZ.dump
```

恢复脚本会：

1. 校验 SHA-256（存在校验文件时）；
2. 默认停止 API、Scheduler 和完整手机号导出 worker；
3. 使用 `pg_restore --exit-on-error --clean --if-exists`，任一 SQL 错误立即失败；
4. 用 `psql -v ON_ERROR_STOP=1 -c "SELECT 1"` 检查数据库基本可连接性；
5. **无论成功或失败，默认都保持 API、Scheduler 和完整手机号导出 worker 停止**，等待完整的 revision、数据对账和业务冒烟。

只有在隔离演练环境、且已经有额外自动验证包围恢复命令时，才允许显式设置 `RESTORE_RESTART_SERVICES=YES` 让成功恢复后自动重启。正式生产回滚默认不得设置该变量。

恢复后执行：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm -T -e RUN_DB_MIGRATIONS=false api \
  python -m alembic -c alembic.ini current --check-heads

docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm -T -e RUN_DB_MIGRATIONS=false api \
  python scripts/reconcile_v12.py \
  > dist/v12-reconciliation-after-restore.json
python -m json.tool dist/v12-reconciliation-after-restore.json >/dev/null
```

上述检查和核心角色冒烟全部通过后，才手工恢复服务：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d api scheduler lead-export-worker
```

## 3. 对象存储

生产使用腾讯云 COS 上海地域私有 Bucket，并启用：

- 服务端加密；
- 版本控制或不可变备份；
- 最小权限 IAM；
- 访问审计；
- 生命周期策略；
- 删除保护或双人审批。

证据文件不得使用永久公网 URL。恢复后需验证数据库中的 `object_key`、`sha256`、文件大小与实际对象一致。

仅当 `OBJECT_STORAGE_BACKEND=local` 时使用本地脚本：

```bash
sh scripts/backup_private_storage.sh
CONFIRM_RESTORE=YES sh scripts/restore_private_storage.sh \
  backups/private-storage/private-storage-*.tar.gz
```

本地存储正式全量前必须完成异地同步和恢复演练。

## 4. 密钥和配置备份

以下内容不得进入 Git 或普通备份压缩包，应保存在企业密钥管理系统：

- `JWT_SECRET`；
- `FIELD_ENCRYPTION_KEY`；
- `PHONE_HASH_SECRET`；
- `PHONE_FINGERPRINT_SECRET`；
- PostgreSQL、微信、飞书和对象存储凭据；
- 正式 TLS 私钥。

`FIELD_ENCRYPTION_KEY` 丢失会导致历史手机号无法解密；`PHONE_FINGERPRINT_SECRET` 错误更换会破坏去重连续性。两者的恢复必须纳入演练。

## 5. 联合恢复演练

上线前至少执行一次，之后至少每季度执行：

1. 在隔离网络建立空白 PostgreSQL；
2. 校验备份 SHA-256 并恢复数据库；
3. 确认 API/Scheduler 在恢复后仍保持停止；
4. 恢复或挂载对象存储版本；
5. 注入与备份对应的密钥；
6. 执行 `alembic current --check-heads`；
7. 执行 V1.2 reconciliation；
8. 抽查历史手机号指纹、派发单、退回证据、奖励和积分流水；
9. 启动 API/Scheduler，完成真实角色冒烟；
10. 记录 RPO、RTO、失败步骤、人工操作和整改责任人。

## 6. 上线前恢复门禁

以下任一情况为 `NO-GO`：

- 最新备份没有校验文件或校验失败；
- 未保存上线前即时备份；
- 恢复失败后服务被错误自动重启；
- 恢复成功但未完成 revision/reconciliation/冒烟就恢复流量；
- 对象存储版本不可恢复；
- 密钥恢复流程未验证；
- `reconcile_v12.py` 返回非零；
- 实测 RTO 超出业务可接受窗口且没有审批；
- 回滚负责人、命令或停止条件不明确。
