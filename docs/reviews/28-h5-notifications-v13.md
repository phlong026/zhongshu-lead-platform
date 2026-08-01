# H5-005 消息中心 V1.3 代码评审

- 需求：H5 Design System V1.3 / 消息中心
- Figma 节点：`12:30`
- 结论：通过

## 变更范围
- 新增 `notifications-v13.css` 与 `notifications-v13.js`。
- 增加客资、积分、审核、系统分类和未读摘要。
- 复用原通知列表、单条已读和业务深链接口。

## 评审要点
- 未读状态来自后端 `read_at`，不在前端伪造。
- 分类仅用于客户端展示，不改变通知权限和数据范围。
- 批量已读逐条调用现有已读接口，不新增隐式权限。
- 原卡片节点与点击深链事件被移动而非替换。

## 自动检查
- `node --check apps/h5/public/notifications-v13.js`：通过
- `python scripts/check_js.py`：通过（10个JS文件）
- `pytest -q`：38 passed / 2 skipped
- `python scripts/secret_scan.py`：通过
