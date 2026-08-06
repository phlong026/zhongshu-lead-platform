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

恢复脚本会校验 SHA-256、停止 API/Scheduler、执行 `pg_restore --clean --if-exists` 并验证数据库可连接。恢复后不得立即开放业务，必须先执行 Alembic 版本检查和 V1.2 对账。

## 3. 对象存储

生产优先使用私有 S3/COS/OSS，并启用：

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
3. 恢复或挂载对象存储版本；
4. 注入与备份对应的密钥；
5. 执行 `alembic current --check-heads`；
6. 执行 `python scripts/reconcile_v12.py`；
7. 抽查历史手机号指纹、派发单、退回证据、奖励和积分流水；
8. 启动 API/Scheduler，完成真实角色冒烟；
9. 记录 RPO、RTO、失败步骤、人工操作和整改责任人。

## 6. 上线前恢复门禁

以下任一情况为 `NO-GO`：

- 最新备份没有校验文件或校验失败；
- 未保存上线前即时备份；
- 对象存储版本不可恢复；
- 密钥恢复流程未验证；
- `reconcile_v12.py` 返回非零；
- 实测 RTO 超出业务可接受窗口且没有审批；
- 回滚负责人、命令或停止条件不明确。
