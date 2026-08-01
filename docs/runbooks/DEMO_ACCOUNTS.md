# 本地演示账号

> 仅用于开发与验收环境。生产环境必须删除演示账号、关闭 `WECHAT_DEV_MOCK` 并更换所有密钥。

| 角色 | 用户名 | 密码 | 入口 |
|---|---|---|---|
| 超级管理员 | `admin` | `Admin123!` | `/admin/` |
| 平台负责人 | `owner` | `Owner123!` | `/admin/` |
| 运营人员 | `operation` | `Operation123!` | `/admin/` |
| 电销人员 | `telesales` | `Telesales123!` | `/call/` |
| 积分管理员 | `finance` | `Finance123!` | `/admin/` |
| 退回审核员 | `reviewer` | `Reviewer123!` | `/admin/` |
| 加盟商负责人（开发演示） | `franchise_demo` | `Franchise123!` | `/h5/` |

初始化命令：

```bash
python scripts/init_db.py
python scripts/seed_demo.py
```

演示数据包括暂存客资、待核验客资、合格客资、待领取订单、已领取订单、积分账户、充值档位、价格规则和站内消息。
