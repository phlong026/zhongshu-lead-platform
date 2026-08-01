# 备份与恢复

## PostgreSQL

每日全量备份，业务高峰期可增加 WAL/PITR。示例：

```bash
docker compose exec -T db pg_dump -U zhongshu -Fc zhongshu > backup.dump
cat backup.dump | docker compose exec -T db pg_restore -U zhongshu -d zhongshu --clean --if-exists
```

## 证据文件

对象存储开启版本控制或定期同步到隔离备份桶。恢复时必须同时校验数据库中的 `object_key`、文件 SHA-256 和实际对象。

## 恢复演练

至少每季度在隔离环境执行一次数据库、截图和录音的联合恢复演练，并记录恢复时间与抽样校验结果。
