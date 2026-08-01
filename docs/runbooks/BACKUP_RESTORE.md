# V1.0.1 备份与恢复

## PostgreSQL 自动备份

```bash
ENV_FILE=.env BACKUP_RETENTION_DAYS=30 scripts/backup_postgres.sh
```

脚本生成 PostgreSQL 自定义格式备份和 SHA-256 校验文件，并删除超过保留期的旧文件。建议由主机 cron 或云调度每天执行，备份结果同步到异地加密存储。

恢复必须明确确认：

```bash
CONFIRM_RESTORE=YES scripts/restore_postgres.sh backups/postgres/zhongshu-YYYYMMDDTHHMMSSZ.dump
```

默认恢复脚本会停止 API 和 Scheduler，执行 `pg_restore --clean --if-exists`，校验数据库可连接后再恢复服务。

## 本地私有对象存储

仅在 `OBJECT_STORAGE_BACKEND=local` 时使用：

```bash
scripts/backup_private_storage.sh
CONFIRM_RESTORE=YES scripts/restore_private_storage.sh backups/private-storage/private-storage-*.tar.gz
```

生产优先使用开启版本控制、服务端加密、访问审计和生命周期管理的 S3/COS/OSS 私有桶。云对象存储不得通过公开永久 URL 暴露截图、录音或银行回单。

## 恢复演练

至少每季度在隔离环境完成一次联合演练：

1. 恢复 PostgreSQL；
2. 恢复或挂载对象存储；
3. 校验 `object_key`、文件 SHA-256 和实际对象；
4. 抽查积分余额与不可变流水是否一致；
5. 运行 `GET /api/v1/points/reconciliation/{company_id}`；
6. 记录 RTO、RPO、失败原因和整改事项。
