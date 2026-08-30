# 运行维护手册

## 日常检查

1. `/health/ready` 返回 200；
2. `notification_outbox` 不存在持续增长的 FAILED/DEAD，`storage_cleanup_outbox` 不存在持续增长的 FAILED；
3. 待领取订单超过 48 小时的回收作业正常；
4. 数据库磁盘、对象存储容量和备份成功率；
5. 微信公众号 Token、消息模板和飞书 Token 状态；
6. 审计日志中是否存在异常高频导出、查看证据或积分调整。

## 手动作业

```bash
python scripts/run_jobs.py outbox
python scripts/run_jobs.py storage-cleanup
python scripts/run_jobs.py assignment-timeouts
python scripts/run_jobs.py followup-overdue
python scripts/run_jobs.py all
# 仅用于专用 worker 不可用时的单任务应急处理；先停 worker，避免突破单并发资源预算
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml stop lead-export-worker
python scripts/run_jobs.py lead-exports
# 应急处理结束并检查任务/临时空间后再恢复专用 worker
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d lead-export-worker
```

所有作业均具备业务幂等键；通知失败不会回滚已经完成的派发、积分或审核事务。`all` 不处理完整手机号导出；该任务默认只由带 640 MiB 临时空间和心跳健康检查的 `lead-export-worker` 串行消费，手动命令一次也只处理 1 个任务。对象存储清理失败会保持 FAILED 并持续按封顶退避重试，不会恢复已删除的测试业务数据；连续失败 5 次后会记录 error 日志。Bucket、Endpoint 或 Region 与任务入队时不一致时会拒绝删除，必须切回原存储目标处理。

回退到 migration `0013` 前，必须确认 `storage_cleanup_outbox` 中所有任务均为 `DELETED`。存在 PENDING、PROCESSING 或 FAILED 时，`0014` 降级会主动终止，避免丢失唯一的待删除对象键。
