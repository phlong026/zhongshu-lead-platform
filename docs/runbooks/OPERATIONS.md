# 运行维护手册

## 日常检查

1. `/health/ready` 返回 200；
2. `notification_outbox` 不存在持续增长的 FAILED/DEAD；
3. 待领取订单超过 48 小时的回收作业正常；
4. 数据库磁盘、对象存储容量和备份成功率；
5. 微信公众号 Token、消息模板和飞书 Token 状态；
6. 审计日志中是否存在异常高频导出、查看证据或积分调整。

## 手动作业

```bash
python scripts/run_jobs.py outbox
python scripts/run_jobs.py assignment-timeouts
python scripts/run_jobs.py followup-overdue
python scripts/run_jobs.py all
```

所有作业均具备业务幂等键；通知失败不会回滚已经完成的派发、积分或审核事务。
