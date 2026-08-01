# H5-008 退回申请与证据上传 V1.3 代码评审

- 需求：H5 Design System V1.3 / 退回申请
- Figma 节点：`15:30`
- 结论：通过

## 变更范围
- 新增 `return-v13.css` 与 `return-v13.js`。
- 优化三步流程、退回原因、补充说明、截图、录音与提交区。
- 增加本地图片预览、音频文件摘要和材料真实性提示。

## 评审要点
- 双证据必传、文件格式与大小校验继续由原增强层和后端共同执行。
- 退回草稿、上传进度、管理员审核和返积分逻辑不变。
- 图片预览仅使用本地 `ObjectURL`，不上传到第三方或长期缓存。
- 原字段和提交按钮事件被保留，不新增绕过审核的路径。

## 自动检查
- `node --check apps/h5/public/return-v13.js`：通过
- `python scripts/check_js.py`：通过（13个JS文件）
- `pytest -q`：41 passed / 2 skipped
- `python scripts/secret_scan.py`：通过
