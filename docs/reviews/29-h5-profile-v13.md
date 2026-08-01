# H5-006 个人中心 V1.3 代码评审

- 需求：H5 Design System V1.3 / 个人中心
- Figma 节点：`13:30`
- 结论：通过

## 变更范围
- 新增 `profile-v13.css` 与 `profile-v13.js`。
- 展示公司身份、会员等级、当前积分、累计消耗和退回积分。
- 保留消息、积分和退出登录操作。

## 评审要点
- 仅调用当前用户公司范围内的账户和积分流水接口。
- 累计消耗与退回积分由真实流水计算，不在前端写死。
- 不增加其他公司、平台财务或成本字段。
- 原退出登录按钮和事件被移动而非替换。

## 自动检查
- `node --check apps/h5/public/profile-v13.js`：通过
- `python scripts/check_js.py`：通过（11个JS文件）
- `pytest -q`：39 passed / 2 skipped
- `python scripts/secret_scan.py`：通过
