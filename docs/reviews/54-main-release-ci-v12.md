# V1.2 Main Release CI 收口评审

## 背景

V1.2.0 已通过 `release/v1.2.0` 的完整 Release CI 并合并到 `main`。历史 `.github/workflows/v101-release.yml` 仍监听 `main`，会在每次主线更新时重新生成标记为 V1.0.1 的交付包，造成版本与 Artifact 语义污染。

## 本次变更

1. 退休 `.github/workflows/v101-release.yml`；
2. 新增 `.github/workflows/main-release.yml`；
3. `main-release.yml` 不再重复构建发布包，只执行主线完整性验证：
   - 依赖安装与 `pip check`；
   - 临时依赖豁免到期门禁与 `pip-audit`；
   - 全量 pytest；
   - OpenAPI 实时生成；
   - JavaScript、secret scan、Python compile、whitespace 检查；
   - `RELEASE_MANIFEST.json` 版本格式、来源 release 分支、clean-worktree 标志校验；
   - 对应 Release Notes 存在性校验；
   - 明确禁止旧 V1.0.1 main packaging workflow 回归。

## 设计边界

- 正式发布包仍唯一由 `release/v1.2.0` 的 `V1.2 Release Branch CI` 生成；
- `main` 只负责确认被提升的代码树与发布元数据仍自洽，不重复制造第二套发布 Artifact；
- 历史 V1.0.1 文件删除仅影响当前工作树，不删除 Git 历史，可随时追溯旧版本发布记录。

## 验收标准

- PR CI 全绿；
- 新 `Main Release Verification` 工作流可执行成功；
- PR 合并后 `main` 不再触发 `V1.0.1 CI and Package`；
- 合并后不得再生成 `zhongshu-v1.0.1-*` Artifact；
- `main` 仍通过版本/Manifest/Release Notes/安全与测试校验。
