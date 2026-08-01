# H5-001 首页工作台 V1.3 代码评审

## 需求依据

- 《众墅之家 H5 移动端 Design System V1.3》
- Figma 文件：`众墅之家 H5 V1.3 Figma 1:1还原设计稿`
- Figma 首页节点：`6:2`
- 基线分支：`release/v1.0.1`

## 变更范围

- 新增 `apps/h5/public/design-system-v13.css`
- 新增 `apps/h5/public/design-system-v13.js`
- 更新 `apps/h5/public/index.html`
- 新增 `apps/api/tests/test_h5_design_system_v13.py`

## 评审结论

通过。

## 评审要点

1. **业务兼容性**：不修改现有 API、积分事务、派发/领取状态机和权限逻辑；页面增强基于现有 DOM 数据，不生成虚假经营数据。
2. **事件兼容性**：原有节点采用移动而非复制，保留已绑定的领取、路由和客资详情事件；新增快捷入口采用独立事件委托。
3. **视觉一致性**：色彩、字体层级、间距、圆角和卡片结构与 V1.3 Figma 首页一致；继续使用仓库中的正式 Logo 文件。
4. **隔离性**：首页增强使用 `zs-v13-*` 命名空间，避免污染登录、详情、积分、退回等未改造页面。
5. **安全性**：未增加外部脚本、第三方依赖、内联敏感配置或客户信息日志。
6. **可回滚性**：删除新增 CSS/JS 引用即可恢复 V1.0.1 原页面，不涉及数据库迁移。

## 自动检查

- `node --check apps/h5/public/design-system-v13.js`：通过
- `python scripts/check_js.py`：通过，检查 6 个 JavaScript 文件
- `pytest -q`：35 项通过，2 项按环境跳过
- `python scripts/secret_scan.py`：通过，未发现提交密钥

## 已知边界

- 当前评审覆盖首页工作台；客资列表、客资详情、积分中心等页面将在后续任务中逐项按 Figma 设计升级。
- 当前环境无法执行微信内置浏览器真机截图，最终仍需在 UAT 阶段完成 iOS/Android 微信真机视觉回归。
