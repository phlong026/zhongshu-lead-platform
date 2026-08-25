# 本地演示账号

> 仅用于开发与验收环境。生产环境必须删除演示账号、关闭 `WECHAT_DEV_MOCK` 并更换所有密钥。

| 角色 | 用户名 | 密码 | 入口 |
|---|---|---|---|
| 超级管理员 | `admin` | `Admin123!` | `/admin/` |
| 运营管理员 | `operation` | `Operation123!` | `/admin/` 或 `/h5/admin/` |
| 电销人员 | `telesales` | `Telesales123!` | `/h5/call/` |
| 加盟商负责人（开发演示） | `franchise_demo` | `Franchise123!` | `/h5/` |
| 加盟商员工（开发演示） | `franchise_employee_demo` | `Employee123!` | `/h5/` |

初始化命令：

```bash
python scripts/init_db.py
python scripts/seed_demo.py
```

演示数据包括待运营初审、待电销核验、待运营处置、待派发、待领取、已领取订单、积分账户、充值档位、价格规则和站内消息。演示账号均为固定五角色；不再创建历史岗位账号。
