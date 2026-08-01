# H5-004 积分中心 V1.3 代码评审

- 需求：H5 Design System V1.3 / 积分中心
- Figma 节点：`11:30`
- 结论：通过

## 变更范围
- 新增 `points-v13.css` 与 `points-v13.js`。
- 复用原积分账户、充值档位、会员权益与积分流水接口。
- 不修改积分入账、扣减、返还、冲正与权限逻辑。

## 评审要点
- 充值仍为线下付款和管理员人工入账，页面不出现在线支付入口。
- 会员权益由后端已发布档位数据生成，不在前端写死。
- 档位和流水节点采用移动与样式增强，原业务数据保持真实。
- 页面增强采用 `zs-v13-*` 命名空间，可独立回滚。

## 自动检查
- `node --check apps/h5/public/points-v13.js`：通过
- `python scripts/check_js.py`：通过（9个JS文件）
- `pytest -q`：37 passed / 2 skipped
- `python scripts/secret_scan.py`：通过
