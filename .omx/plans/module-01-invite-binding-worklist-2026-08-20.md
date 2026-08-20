# 第一个模块工作任务清单：后台专属邀请与微信确认绑定

日期：2026-08-20
状态：已修订，待开发
评审状态：2026-08-20 第一轮代码对照评审意见已吸收（第 8 节）；**同日第二轮独立复核（代码评审 REQUEST CHANGES / 架构评审 WATCH）指出的 5 项修订稿缺陷已全部修正（第 8.1 节）**。正文中带 **（评审补充 / 评审修正 / 评审新增）** 标记的内容由评审引入，二轮修订以 **（二轮…）** 标记。
范围：公众号 H5 登录/绑定 + PC 后台加盟商邀请，不包含后续手机号自动匹配、地区手动匹配、供应商自行录入流程。
配套文档：[第一个模块开发计划](./module-01-invite-binding-dev-plan-2026-08-20.md)

## 1. 模块目标

第一版采用“后台专属邀请 + 二维码/链接 + H5 预览确认 + 微信 OAuth 绑定”的最小闭环：

- 后台运营在加盟商公司档案中发出专属邀请。
- 邀请展示必须清楚体现“邀请对象/负责人名称 + 公司名称”，降低发错对象的风险。
- 后台弹窗提供复制按钮，复制内容应包含负责人、公司、有效期、邀请链接。
- 后台弹窗提供二维码展示或二维码生成入口，方便微信扫码打开。
- H5 邀请页面在 OAuth 前展示公司摘要，由用户确认后再进入微信授权。
- 复制按钮本轮明确放在后台邀请弹窗；接收方 H5 不提供二次转发专属链接的按钮，避免个人一次性邀请被继续转发。
- 链接 URL 只携带 token，不把姓名、公司、手机号等明文身份信息塞入 URL。
- 第一版默认邀请对象使用公司档案 `owner_name`，公司名称使用 `Company.name`；除非执行评审证明必要，不新增数据库字段。

## 2. 当前实现证据

- `Company` 已有 `name`、`owner_name`、`primary_user_id`，可支撑“公司 + 负责人 + 主微信绑定”第一版信息展示：`apps/api/src/core/models.py:95-106`。
- `InviteToken` 当前仅保存 token hash、公司、过期、使用、撤销、创建人，没有邀请展示字段：`apps/api/src/core/models.py:165-174`。
- 后台已有创建邀请接口，返回 `invite_id`、原始 token、URL、过期时间：`apps/api/src/routers/auth.py:147-158`。
- 后台已有撤销接口，但当前没有邀请列表页/记录页：`apps/api/src/routers/auth.py:161-173`。
- H5/OAuth start 会校验邀请有效性并把 invite 写入 signed state：`apps/api/src/routers/auth.py:188-210`。
- OAuth callback 当前会直接调用 `login_or_bind_wechat` 并完成绑定：`apps/api/src/routers/auth.py:213-238`。
- 邀请预览接口已返回 `company_name`、`owner_name`、服务地区、业务范围、等级、`expires_at`，且不返回手机号/积分：`apps/api/src/routers/invite_preview.py:17-40`；测试已覆盖安全摘要：`apps/api/tests/test_invite_preview.py:6-29`。**（评审补充：`expires_at` 已存在，H5 确认卡展示有效期无需新增字段。）**
- 绑定服务已经实现一次性 token 消费，`used_at is null` 的条件更新是并发边界：`apps/api/src/services/auth_service.py:253-290`。
- 新微信首次使用邀请时会创建 `FRANCHISE_OWNER` 用户，并写入 `company.primary_user_id`：`apps/api/src/services/auth_service.py:320-337`。
- 后台公司页已有“邀请”入口，但弹窗只有 textarea，文案提到二维码但未生成，也没有复制按钮：`apps/admin/public/app.js:46`。
- H5 登录页基础文案仍是“授权后自动绑定”：`apps/h5/public/app.js:36-39`。
- H5 增强层已有邀请预览卡和服务规则勾选，但按钮仍承接原点击逻辑：`apps/h5/public/status-pages-v13.js:18-39`；预览失败时会 `btn.disabled=true`：`apps/h5/public/status-pages-v13.js:40`。**（评审补充：`disabled` 是现有的半个门禁，改造时不得丢失。）**
- `enhancements.js` 会再次重写微信登录按钮并直接进入 `/auth/wechat/start`，确认链路必须统一收口，不能只修改其中一个脚本：`apps/h5/public/enhancements.js:64-75`、`apps/h5/public/enhancements.js:156-169`。
- 安全测试已覆盖 OAuth state、防开放跳转、邀请重放、跨公司绑定拒绝：`apps/api/tests/test_pre_go_live_security.py:450-530`。

### 2.1 评审补充证据（2026-08-20 文档评审新增）

以下事实在初版清单中缺失，直接影响 P0 任务的可执行性与验收有效性：

- **存在第二条无确认绑定路径**：`POST /auth/wechat/mock-callback` 经 `bind_wechat_by_invite` 直达 `login_or_bind_wechat`，完全不经过 signed state：`apps/api/src/routers/auth.py:176-186`、`apps/api/src/services/auth_service.py:339-340`。开关 `wechat_dev_mock` 默认值为 `True`：`apps/api/src/core/config.py:42`。**（二轮分级修正：`apps/api/src/core/production.py:67` 会把 `wechat_dev_mock=True` 列为生产启动阻断错误，生产环境起不来——因此这不是现存生产绕过漏洞，而是开发/测试/预发环境绑定合同与生产不一致的问题；代码风险「中」，文档层面的用例矛盾（原 §6 拿它当正向绑定用例）才是阻塞项。）**
- **邀请消费以 raw token 为查找键**：`_validate_invite` 与 `_consume_invite` 均按 `hash_token(raw)` 查询：`apps/api/src/services/auth_service.py:241-242`、`apps/api/src/services/auth_service.py:253-290`。state 改为只带 `invite_id` 后，消费入口必须同步改造。
- **后台点击「邀请」即刻创建 token**，无任何二次确认：`apps/admin/public/app.js:46`。
- **`with_for_update()` 在 SQLite 上是 no-op**，所有依赖行锁的并发验收只能由 PostgreSQL 提供证据；仓库现有可参考夹具：`apps/api/tests/test_internal_user_postgres_concurrency_e2e.py`。
- **`purpose` 是 `decode_signed_state` 唯一的类型校验**，`expires_minutes` 默认已为 10：`apps/api/src/core/security.py:147-163`。
- **前端自包含测试只扫 `index.html` 的 `src`/`href`**，不覆盖 js 内动态注入的外链：`apps/api/tests/test_frontend_contract.py:27-38`。
- **H5 确认门禁靠 script 标签顺序撑住**：`enhancements.js` 对 `#wechat-login` 是直接赋值覆盖（`apps/h5/public/enhancements.js:64-75`），`status-pages-v13.js` 是包装原 handler（`apps/h5/public/status-pages-v13.js:35`）；两者都挂 `MutationObserver` 到 `document.documentElement`（`apps/h5/public/enhancements.js:163`、`apps/h5/public/status-pages-v13.js:50`）。当前不出事仅因 `apps/h5/public/index.html:29` 先于 `:39` 加载，任何加载顺序调整都会静默删除勾选门禁，且无测试会红。
- **公司状态判定两条路径不一致**：创建邀请用 `status == "DISABLED"` 拒绝（`apps/api/src/services/auth_service.py:227`），预览/绑定用 `status != "ACTIVE"` 拒绝（`apps/api/src/services/auth_service.py:248`、`apps/api/src/routers/invite_preview.py:29`）。
- **`revoke_invite` 对不存在的 invite 静默返回成功**：`apps/api/src/routers/auth.py:161-173`。
- **事务回滚是隐式的**：无全局 `AppError` → rollback 处理器，靠 `get_db` 的 `session.close()` 兜底：`apps/api/src/core/database.py:34-39`。
- **应用层访问日志已关闭**：`uvicorn.access` 被 `disabled = True`：`apps/api/src/core/logging.py:48-51`；query string 中的 raw token 残留风险只在反向代理层。
- **`Company.owner_name` 可为空**：`apps/api/src/core/models.py:102`，`copy_text` 必须有降级文案分支。
- **仓库工作树长期非干净（二轮改写为检查动作，快照已删除）**：该仓库存在并行的 V1.2 整改工作，`fix/v12-remediation-closure` 分支上不定期有未提交改动，且文件集合随时间变化——第一轮写死的具体文件清单在评审期间即已过期。开工时必须实际运行 `git status --short --branch` 并用 `git diff --name-only` 与本模块目标文件取交集判断是否冲突，不得采信任何历史快照。

## 3. P0 必须修改

### P0-01 后台创建邀请返回可直接展示的收件信息

影响文件：

- `apps/api/src/routers/auth.py`
- `apps/api/src/services/auth_service.py`
- `apps/api/tests/test_auth_company.py`

任务：

- 创建邀请接口返回 `company_name`、`owner_name`、`copy_text`、`expires_at`、`url`。
- `copy_text` 格式统一，模板串为：`{owner_name}，您好：这是【{company_name}】的微信绑定邀请，请在微信内打开：{url}，有效期至：{expires_at}`。渲染示例：`张老板，您好：这是【上海测试加盟商】的微信绑定邀请，请在微信内打开：{url}，有效期至：{expires_at}`。
- **（评审补充 L2，二轮措辞收紧）** `Company.owner_name` 可为空（`apps/api/src/core/models.py:102`），必须有降级分支：`owner_name` 为空或空串时，`copy_text` 开头改为 `您好：这是【{company_name}】的微信绑定邀请……`，`owner_name` 字段返回 `null` 而非空串，由前端展示为「未填写负责人」。上一行的姓名是模板渲染示例，非字面量要求。
- 不返回完整手机号，不在 URL 拼接姓名或公司名。

验收：

- 接口响应包含 `company_name`、`owner_name`、`copy_text`。
- `url` 仍只包含 `invite={token}`。
- 测试断言 `copy_text` 包含负责人和公司名，且不包含 `contact_phone` 或明文手机号。

### P0-02 后台邀请弹窗增加复制按钮和清晰信息块

影响文件：

- `apps/admin/public/app.js`
- `apps/admin/public/styles.css`
- `apps/api/tests/test_frontend_contract.py`

任务：

- 弹窗顶部展示：邀请对象、公司名称、有效期。
- 增加“复制完整邀请文案”和“复制链接”两个按钮。
- 复制成功/失败均有 toast；浏览器不支持 `navigator.clipboard` 时降级选中 textarea。
- 保留 textarea，但默认填充完整邀请文案，不只放裸链接。
- 增加“撤销本次邀请”按钮；发现点错公司或发错对象时可立即调用现有撤销接口。

验收：

- 静态合同测试能找到 `navigator.clipboard.writeText` 或降级复制逻辑。
- 弹窗 HTML 中能找到 `company_name`、`owner_name`、`copy_text` 使用点。
- 运营可以一键复制完整文案或纯链接。
- 撤销后当前链接不能继续预览、进入 OAuth 或完成绑定。

### P0-03 后台邀请弹窗生成二维码

影响文件：

- `apps/admin/public/app.js`
- `apps/admin/public/index.html`
- `apps/admin/public/styles.css`
- `apps/admin/public/vendor/qrcode.min.js`
- `apps/admin/public/vendor/QR-LICENSE.txt`
- `apps/api/tests/test_frontend_contract.py`

任务：

- 在弹窗中展示二维码区域，二维码内容为邀请 URL。
- 固定采用本地 vendored、经许可证和版本审查的轻量二维码 JS 库；不手写二维码算法，不调用 CDN、在线二维码接口或第三方图片服务。
- 将固定版本文件和许可证说明放入 `apps/admin/public/vendor/`，由后台 `index.html` 本地加载。
- 二维码区域必须同时保留可复制链接，避免二维码生成失败时无法发送。
- **（评审补充）** 在 `apps/api/tests/test_frontend_contract.py` 新增一条测试：`apps/admin/public/` 下所有 `*.js` 全文不得出现 `http://` 或 `https://`。现有自包含测试只扫 `index.html` 的 `src`/`href`，挡不住 js 内动态注入 `script.src` 的 CDN 引用。
- **（评审补充）** 记录 `vendor/qrcode.min.js` 的 SHA-256 到测试常量中并断言一致。存在性测试挡不住供应链投毒，Pre-mortem Failure 3 的预防措施必须升级为完整性校验。

验收：

- 邀请弹窗可看到二维码容器和链接。
- 无外部 CDN 运行时依赖。**（评审修正：不能只引用 `apps/api/tests/test_frontend_contract.py:27-38` 作为依据，该测试只覆盖 `index.html`；必须由新增的 admin js 全文外链扫描测试提供证据。）**
- 静态合同验证 vendor 文件存在 **且 SHA-256 与记录值一致**，二维码内容与接口返回的邀请 URL 完全一致。
- 二维码生成失败时不影响复制按钮。

### P0-04 H5 邀请页从“自动绑定”改成“确认后授权绑定”

影响文件：

- `apps/h5/public/app.js`
- `apps/h5/public/enhancements.js`
- `apps/h5/public/status-pages-v13.js`
- `apps/h5/public/status-pages-v13.css`
- `apps/api/tests/test_frontend_contract.py`
- `apps/api/src/routers/auth.py`
- `apps/api/src/schemas/auth.py`
- `apps/api/tests/test_wechat_oauth.py`

任务：

- 将基础文案“授权后自动绑定”调整为“确认公司信息后授权绑定”。
- 邀请预览卡明确展示 `公司名称 + 负责人 + 服务地区 + 业务范围 + 等级`。
- 用户未勾选规则/未确认时不能跳转 OAuth；`app.js`、`status-pages-v13.js`、`enhancements.js` 必须共享同一个确认状态和唯一跳转入口。
- 用户确认后调用 `POST /api/v1/auth/invites/confirm-start`，请求体为 `{"invite":"<raw-token>","return_url":"/h5/#/home"}`；后端校验邀请并返回 `{"authorization_url":"<wechat-oauth-url>","expires_at":"<iso-time>"}`。
- OAuth signed state 只携带 `invite_id`、`company_id`、`binding_confirmed=true`、`return_url`，不再携带 raw invite token；callback 只有在 signed state 表明该邀请已确认时才允许新用户绑定。
- **（评审建议 H1，二轮措辞收紧为推荐而非唯一解）** confirmation intent 推荐使用独立 `purpose="wechat-oauth-bind"`：`purpose` 是 `decode_signed_state` 唯一的类型校验（`apps/api/src/core/security.py:158-163`），用它分流可让"旧 state 冒充确认 state"在 decode 阶段就失败。复用 `purpose="wechat-oauth"` 并在 callback 严格校验 `binding_confirmed is True` 也可安全实现；若选复用，PR 必须写明理由并补一条「payload 缺少 `binding_confirmed` 时拒绝」的负例测试。callback 按 purpose 分流：bind purpose（或带确认标记）才允许首次绑定，legacy purpose 只允许已绑定登录。
- **（评审修正 H1）** 有效期沿用 `create_signed_state` 的 `expires_minutes` 默认值 10，不新增参数、不自行传值。
- **（评审修正 B2）** `_consume_invite` 增加按 `invite_id` 消费的入口：条件更新的 `where` 从 `token_hash ==` 改为 `id ==`，**但 `used_at IS NULL`、`revoked_at IS NULL`、`expires_at > now` 三个条件必须原样保留**——那是一次性消费的并发边界，不得弱化。`_validate_invite` 同步支持 invite_id 查找。不做这一步，state 去 raw token 的改造无法落地。
- **（评审修正 H2，二次核查后改写）** `/auth/wechat/start` 的 `invite` 参数处置分两步，**缺一不可**：
  1. 移除函数签名中的 `invite` 参数及其校验分支（`apps/api/src/routers/auth.py:188-210`），H5 三个脚本同步清掉拼接 `invite=` 的代码。
  2. **增加显式拒绝逻辑**：从 `request.query_params` 检测到 `invite` 键时直接返回 `AUTH_INVITE_ENTRY_DEPRECATED` 400，提示"请从最新邀请链接重新进入"。
  第 2 步是必需的——实测确认 FastAPI 对未声明的 query 参数**直接忽略并返回 200**（`GET /start?invite=<raw>` → `200`，参数被丢弃）。只删签名不会拒绝旧 URL，只会让旧链接静默走完一次 OAuth 跳转、最后在 callback 因 `invite_token=None` 失败，用户看到的是"授权失败"而非"链接已过期"。注意：**这不是安全漏洞**（首次绑定仍然失败），是可诊断性与合同清晰度问题。
  说明：H2 的表述也需收紧——H5 当前**仍在合法调用** `/wechat/start?invite=`（`apps/h5/public/app.js:39`、`apps/h5/public/enhancements.js:74`），准确说法是"confirm-start 落地后该参数不再需要"，而非"已无合法调用方"。因此本项必须排在 confirm-start 与 H5 改造之后。
- **（评审修正 B1，二轮定版）** 处置 `POST /auth/wechat/mock-callback` 这条绕过路径：该接口经 `bind_wechat_by_invite` 直达绑定，完全不经过 signed state（`apps/api/src/routers/auth.py:176-186`），且 `wechat_dev_mock` 默认为 `True`（`apps/api/src/core/config.py:42`），staging/测试环境默认开启（生产启动守卫会阻断该开关，详见第 2.1 节二轮分级修正）。**已定版方案 A（2026-08-20 拍板）：mock-callback 同样要求携带后端签发的 confirmation intent**，使 dev/test/staging 与生产的绑定合同一致。执行者不得自行改用其他方案；如需变更须走计划变更流程并同步修改两份文档的相应条目。
- 邀请失效时禁用授权按钮并展示"请联系平台重新获取邀请"。

验收：

- H5 入口不再出现“自动绑定”的强承诺文案。
- 有邀请 token 时先请求 `/auth/invites/preview` 并展示摘要。
- 无邀请、邀请无效、预览未完成或用户未确认时不进入微信 OAuth。
- 新微信只有携带后端签发的短时 confirmation intent 才能完成绑定；伪造或过期 intent 返回明确错误。
- **（评审补充 B1）** `wechat_dev_mock=True` 时，不带 confirmation intent 的 mock-callback 被拒绝。此负例必须存在，否则上一条验收不成立。
- **（评审修正 H2，二次核查后改写）** 验收必须是**行为断言**，不能只查 schema：`GET /auth/wechat/start?invite=<任意值>` 返回 400 且错误码为 `AUTH_INVITE_ENTRY_DEPRECATED`。仅断言"OpenAPI 中参数消失"是无效验收——FastAPI 会忽略未声明参数并返回 200，schema 干净但旧 URL 照样被受理。schema 断言可作为辅助项保留，不得作为唯一证据。
- **（评审补充 H3）** 静态合同测试断言：`apps/h5/public/` 三个脚本中，对 `#wechat-login` 的 `onclick` 赋值或 `addEventListener` 注册**合计只出现一处**。原表述"共享同一个确认状态和唯一跳转入口"人工与机器都无法判定，必须改成可 grep 计数的形式。
- confirmation intent 的 request/response 契约进入 OpenAPI 与自动化测试，执行者不得自行更换路径或字段。

### P0-05 防止已绑定公司被新邀请静默覆盖主账号

影响文件：

- `apps/api/src/services/auth_service.py`
- `apps/api/src/routers/auth.py`
- `apps/api/tests/test_auth_company.py`
- `apps/api/tests/test_pre_go_live_security.py`
- `apps/api/tests/test_invite_binding_postgres_concurrency_e2e.py`
- `scripts/run_v12_e2e.py`

任务：

- 第一版采用最简单规则：公司已存在 `primary_user_id` 且不是当前 openid 对应用户时，新的邀请绑定不得覆盖，返回明确错误。
- 主账号占用必须使用数据库条件更新，例如仅在 `primary_user_id IS NULL` 时写入；禁止使用“先读取为空、再普通赋值”的竞态实现。
- 已绑定微信重新打开同公司新邀请时允许登录，并消费邀请或提示“已绑定，无需重复绑定”，执行阶段二选一并用测试锁定。
- 创建新邀请时如公司已有主账号，后台需要提示当前绑定状态，避免误发。

验收：

- 同公司已有 `primary_user_id` 时，另一个 openid 使用新邀请不会替换 `primary_user_id`。
- 同一公司两条不同 token 被两个 openid 并发消费时，只能有一个主账号绑定成功；失败事务不得残留第二个用户、角色或微信身份。
- **（评审补充 M2）** 上一条必须由显式断言测试锁定：占用失败后 `select(User).where(company_id=...)` 计数为 1、`WechatIdentity` 计数为 1。当前回滚是隐式的——没有全局 `AppError` → rollback 处理器，靠 `get_db` 的 `session.close()` 兜底（`apps/api/src/core/database.py:34-39`）。行为正确，但一旦有人给 `get_db` 加 `commit()` 或改用 middleware 管理会话即静默破功，必须有测试守住。实现时在代码注释中标注该依赖。
- 新增 PostgreSQL 专项测试并加入 `scripts/run_v12_e2e.py` 的 `TARGET_TESTS`；默认 SQLite 测试不能替代该证据。
- 现有跨公司绑定拒绝测试仍通过。
- 失败响应可映射到 H5 `bound_other` 或“公司已绑定”状态页。

### P0-06 同公司只保留一个有效主账号邀请

影响文件：

- `apps/api/src/services/auth_service.py`
- `apps/api/src/routers/auth.py`
- `apps/api/tests/test_auth_company.py`
- `apps/api/tests/test_pre_go_live_security_review.py`
- `apps/api/tests/test_invite_binding_postgres_concurrency_e2e.py`
- `scripts/run_v12_e2e.py`

任务：

- 创建邀请时锁定目标公司；如公司已有主账号，拒绝创建新的主账号邀请。
- 对未绑定公司生成新邀请时，在同一事务内撤销该公司其他未使用、未过期、未撤销邀请，再创建新邀请。
- 旧链接统一返回邀请失效，不泄露“被哪条新邀请替换”等内部信息。
- **（评审补充 M1）** 统一公司状态判定：`create_company_invite` 当前用 `company.status == "DISABLED"` 拒绝（`apps/api/src/services/auth_service.py:227`），而预览/绑定用 `status != "ACTIVE"` 拒绝（`:248`、`apps/api/src/routers/invite_preview.py:29`）。中间态公司能创建出必然预览失败的邀请。本任务已改创建路径，顺手统一为 `!= "ACTIVE"`。

验收：

- 同公司连续生成两次邀请后，第一条邀请不可再预览或绑定。
- 两个管理员并发生成邀请时，提交完成后最多只有一条有效邀请。**（评审修正 B4，二轮措辞收紧：本条只承认 PostgreSQL 证据——「创建邀请时锁定目标公司」依赖 `SELECT ... FOR UPDATE`，而 `with_for_update()` 在 SQLite 上是 no-op，SQLite 下的结果无论通过还是报 database is locked 都不能作为行锁语义的证据。测试须放入 `apps/api/tests/test_invite_binding_postgres_concurrency_e2e.py` 并纳入 `scripts/run_v12_e2e.py` 的 `TARGET_TESTS`。）**
- **（评审补充 M1）** 非 `ACTIVE` 状态公司无法创建邀请，错误与预览路径一致。
- 自动撤销写入审计，但审计不得记录原始 token 或包含 token 的复制文案。

### P0-07 保留并强化邀请一次性和跨公司安全测试

影响文件：

- `apps/api/tests/test_auth_company.py`
- `apps/api/tests/test_pre_go_live_security.py`
- `apps/api/tests/test_wechat_oauth.py`

任务：

- 扩充测试覆盖同公司多邀请、不同 token 并发、已绑定公司再次邀请、确认 intent 伪造/过期、邀请撤销后预览/授权失败。
- 保留现有重放、跨公司、state tamper/open redirect 测试。

验收：

- 相关认证测试单独运行通过。
- 安全负例不会因为 UI 修改而弱化。

### P0-08 邀请生成前的二次确认（评审新增，自 P1-03 上提）

上提理由：后台点击「邀请」是**立即** POST 创建 token，无任何确认（`apps/admin/public/app.js:46`）；而 P0-06 要求「生成新邀请时同一事务内撤销该公司其他有效邀请」。两者叠加后，运营点错一次公司，就会**立刻作废该公司已发出、对方尚未使用的那条邀请**，且开发计划第 7 节明确规定该撤销不随代码回滚恢复、禁止手工清空 `revoked_at`。**（二轮措辞收紧：该 token 不可恢复，但运营可重新生成新邀请补救，准确说法是「误操作代价高且无法原地撤销」，不是「完全不可逆」。）** P0-06 引入的破坏性副作用只能由本任务兜住，留在 P1 属优先级错配。

影响文件：

- `apps/admin/public/app.js`
- `apps/api/tests/test_frontend_contract.py`

任务：

- 点击「邀请」后先弹出确认框，展示「将为【公司名称】的负责人【负责人姓名】生成新的绑定邀请」，并在该公司已存在有效邀请时明确提示「生成后原邀请将立即失效」。
- 用户确认后才发起创建请求；取消不产生任何后端调用。

验收：

- 静态合同测试能找到确认步骤，且创建邀请的请求不在「邀请」按钮的直接 onclick 中发出。
- 取消确认后不产生 `INVITE_CREATE` 审计记录。
- 已有有效邀请的公司，确认框包含「原邀请将立即失效」字样。

## 4. P1 应尽快补齐

### P1-01 后台邀请记录列表

影响文件：

- `apps/api/src/routers/auth.py`
- `apps/admin/public/app.js`
- `apps/admin/public/styles.css`

任务：

- 在公司邀请弹窗或公司详情中展示最近邀请记录：创建时间、创建人、过期时间、状态（有效/已使用/已撤销/已过期）。
- 提供撤销按钮，调用现有 `/auth/invites/{invite_id}/revoke`。
- **（评审补充 M4）** 修复 `revoke_invite` 的静默成功：当前 `if invite:` 之外没有 else 分支，对不存在的 invite 也返回「邀请已撤销」（`apps/api/src/routers/auth.py:161-173`）。把撤销按钮暴露给运营后，撤销失败会看起来像成功。改为不存在时返回 404，或在响应体中返回 `revoked: true/false` 由前端区分。

验收：

- 运营能看到最近邀请状态，避免重复发送未知状态链接。
- 已撤销邀请无法预览、无法 start OAuth、无法 callback 绑定。
- **（评审补充 M4）** 撤销不存在的 invite_id 返回明确失败，前端不显示「已撤销」成功提示。

### P1-02 邀请使用结果与绑定账号追溯

影响文件：

- `apps/api/src/routers/auth.py`
- `apps/admin/public/app.js`

任务：

- 在邀请记录中展示是否已使用、使用时间以及最终绑定的主账号名称。
- 第一版若无法从现有数据可靠还原使用者，只展示可证实字段；不要用当前 `primary_user_id` 冒充历史快照。

验收：

- 运营能够区分“邀请已使用”和“当前主账号是谁”；无法证实的历史字段明确显示为“未记录”。

### P1-03 邀请发送前的二次确认 —— **已于 2026-08-20 文档评审上提为 P0-08，本条作废**

上提理由见 P0-08。原内容保留仅为追溯，不再作为 P1 排期项。

### P1-04 H5 错误状态页补齐

影响文件：

- `apps/h5/public/status-pages-v13.js`
- `apps/h5/public/status-pages-v13.css`

任务：

- 统一处理邀请失效、公司停用、当前微信已绑定其他公司、公司已有主账号等状态。
- OAuth callback 后的错误要能被用户理解并返回重新获取邀请。

验收：

- 每一种认证错误都有清晰页面，不暴露 token、openid、手机号等敏感信息。

## 5. P2 后续迭代

### P2-01 邀请对象快照字段

默认不做。只有当业务要求“邀请发出后，即使公司负责人被后台改名，也要保留当时发送对象”时，再新增 `invitee_name_snapshot`、`company_name_snapshot` 等字段并做迁移。

### P2-02 手机号自动匹配与手动匹配

本次不做。待专属邀请稳定后，再规划微信手机号授权、系统手机号 hash 匹配、地区选择/手动指定供应商匹配。

### P2-03 邀请发送渠道集成

本次不直接接微信模板消息、短信或企业微信。第一版先由后台生成文案、链接和二维码，人工发送。

## 6. 主要风险

- 绑定覆盖风险：当前服务会写 `company.primary_user_id`，必须先锁定“不能静默覆盖”的测试。
- 链接误发风险：后台必须突出负责人/公司，并支持复制完整文案。
- 确认绕过风险：三个 H5 脚本都会接触微信登录按钮，必须统一事件入口，并由后端 signed confirmation intent 证明用户已确认。
- 二维码依赖风险：现有前端自包含测试禁止外部 CDN，二维码固定使用本地受审查 vendor 文件，失败时复制链路仍可用。
- OAuth 现场风险：历史记录显示真实服务号网页授权域名配置仍是上线验收门槛，不能用本地 mock 代表生产通过。
- PII 泄露风险：URL 只放 token，预览接口不返回手机号/积分，日志与 audit 不记录原始 token。

以下为 2026-08-20 文档评审新增风险：

- **mock-callback 旁路风险（二轮分级修正）**：`/auth/wechat/mock-callback` 是一条不经过 signed state 的绑定路径，`wechat_dev_mock` 默认开启——但生产启动守卫会阻断该开关，因此**不构成生产绕过**；不处置的问题是 dev/test/staging 与生产的绑定合同不一致，预发无法验证真实确认链路。已定版方案 A（要求 confirmation intent）。
- **假绿灯风险**：`with_for_update()` 在 SQLite 上是 no-op，行锁相关验收若不指定 PostgreSQL，其通过不能作为行锁语义的证据。
- **误发高风险**：P0-06 的自动撤销 + 后台无二次确认 = 点错公司即作废他人有效邀请（token 不可恢复，可重新生成补救）。已由 P0-08 兜底，且二者在开发计划 Phase 2 同批交付。
- **加载顺序脆弱性风险**：H5 勾选门禁靠 `index.html` 的 script 标签顺序撑住，`enhancements.js` 用赋值而非包装。任何加载顺序调整会静默删除门禁，且现有测试全绿。
- **供应链风险升级**：vendor 文件的存在性测试挡不住投毒，须以 SHA-256 完整性校验替代。
- **反向代理日志风险（二轮升级为已确认）**：实测 `infra/nginx/default.conf` 无任何 `access_log` 指令、仅一个 `location /` 全量反代，继承 nginx 默认 combined 格式（`$request` 含 query string）——因此 `GET /auth/invites/preview?invite=<raw>` 在当前仓库配置下**确定会写入 nginx 日志**，不是假设。整改项与生产宝塔配置复测要求见开发计划 §6 Observability。

## 7. 完成定义

- P0 任务全部完成并有测试覆盖。
- 后台可生成邀请、复制完整文案、复制链接、展示二维码。
- H5 能在 OAuth 前展示公司/负责人并由用户确认。
- OAuth 首次绑定不能绕过服务器签发的确认 intent。
- 旧邀请重放、跨公司绑定、已绑定覆盖、同公司不同 token 并发、撤销邀请均被拒绝。
- 二维码库仅本地加载，版本与许可证已记录，不存在外部运行时依赖。

以下为 2026-08-20 文档评审新增的完成条件：

- mock-callback 已按定版方案 A 要求 confirmation intent（2026-08-20 拍板），并有负例测试。
- **（二轮改写）** `GET /auth/wechat/start?invite=<任意值>` 返回 400 且错误码为 `AUTH_INVITE_ENTRY_DEPRECATED`——行为断言是唯一有效验收，OpenAPI 中参数消失仅作辅助证据。
- confirmation intent 采用独立 `purpose="wechat-oauth-bind"`（若复用须按 H1 记录理由并补负例）。
- 所有依赖行锁的并发验收由 `scripts/run_v12_e2e.py` 实际执行的 PostgreSQL 测试提供证据，skip 不算通过。
- 三个 H5 脚本中对 `#wechat-login` 的事件绑定合计只有一处，由静态合同测试计数守住。
- admin js 全文外链扫描测试通过，vendor 二维码库 SHA-256 与记录值一致。
- 后台生成邀请前有二次确认（P0-08）。

## 8. 评审备注（2026-08-20）

本节独立记录本次文档评审的结论与去向，正文中所有由评审引入的改动均以 **（评审补充 / 评审修正 / 评审新增）** 标记，可与初版内容区分。

评审方式：逐条核对初版清单第 2 节的代码引用。结论——初版引用**基本准确**，仅两处偏差（预览接口漏记 `expires_at`、H5 增强层漏记 `btn.disabled` 门禁），已在正文修正。风险识别到位，静默覆盖、确认绕过、二维码供应链三个核心风险均已抓住。以下为初版缺失、且会导致执行受阻或验收失效的问题。

| 编号 | 级别 | 问题 | 去向 |
|---|---|---|---|
| B1 | 阻塞 | `mock-callback` 是确认门禁的完整绕过路径，两份文档均未覆盖；且开发计划 §6 把它当作正向用例，与 P0-04 验收直接冲突（二轮分级：生产守卫已阻断，代码风险实为「中」，阻塞项是文档用例矛盾） | P0-04 新增处置任务与负例验收；风险表新增条目；二轮定版方案 A |
| B2 | 阻塞 | state 改为只带 `invite_id`，但 `_consume_invite` / `_validate_invite` 仍以 raw token 为查找键，无对应改造任务，执行者必然卡住 | P0-04 新增 `_consume_invite` 改造任务，明确保留三个并发边界条件 |
| B3 | 阻塞 | P0-06 的自动撤销 + 后台无二次确认 = 误操作即作废他人有效邀请（二轮收紧：token 不可恢复但可重新生成，非「完全不可逆」）；二次确认留在 P1 属优先级错配 | P1-03 上提为 P0-08；二轮进一步要求与自动撤销在 Phase 2 同批交付且先合入 |
| B4 | 阻塞 | 「并发创建邀请只剩一条」未指定 PostgreSQL，SQLite 结果不能作为行锁证据 | P0-06 验收补「只承认 PostgreSQL 证据」 |
| H1 | 高 | confirmation intent 复用 `purpose="wechat-oauth"`，靠字段缺失做安全判定（二轮收紧：复用 + 严格 `is True` 校验亦可安全实现，独立 purpose 是推荐加固而非唯一解） | P0-04 改为推荐独立 purpose + 复用须记录理由并补负例 |
| H2 | 高 | `/wechat/start` 的 `invite` 参数在 confirm-start 落地后不再需要（二轮修正：H5 当前仍在合法调用，不能说「已无合法调用方」；且仅删参数不会拒绝旧 URL，FastAPI 忽略未声明参数返回 200） | 新增显式拒绝 `AUTH_INVITE_ENTRY_DEPRECATED` + 行为断言验收；排在 H5 改造之后 |
| H3 | 高 | `enhancements.js` 是覆盖者不是包装者，门禁靠 script 标签顺序撑住；原验收不可机器判定 | 第 2.1 节补机制证据；P0-04 验收改为可 grep 计数 |
| H4 | 高 | P0-03 验收引错依据（自包含测试只覆盖 `index.html`）；存在性测试挡不住供应链投毒 | P0-03 新增 admin js 全文外链扫描 + SHA-256 校验 |
| M1 | 中 | 公司状态判定两条路径不一致（`== "DISABLED"` vs `!= "ACTIVE"`） | P0-06 顺手统一 |
| M2 | 中 | 事务回滚是隐式的（靠 `session.close()`），无测试守 | P0-05 验收补显式计数断言 |
| M3 | 中 | 证据引用两处偏差 | 第 2 节已就地修正 |
| M4 | 中 | `revoke_invite` 对不存在的 invite 静默返回成功 | P1-01 新增修复任务 |
| M5 | 中 | 当前分支基线不满足 Phase -1 前置条件（二轮修正：第一轮快照在评审期间即过期，改为规定检查动作） | 开发计划 Phase -1 与第 2.1 节均改为「实际运行 git status + diff 取交集」 |
| L1 | 低 | 反向代理可能记录 query string 中的 raw token | 风险表新增条目；开发计划 §6 Observability 补检查项 |
| L2 | 低 | `copy_text` 示例含硬编码姓名，且未定义 `owner_name` 为空的分支 | P0-01 改为模板串 + 降级文案 |
| L3 | 低 | 估算偏乐观，Phase 0 的 PostgreSQL 并发夹具给 0.5-1 天偏紧（二轮注：工期属估算判断，非源码可证实的缺陷） | 开发计划 §8 调整 |

### 8.1 第二轮评审修订（2026-08-20，独立代码评审 REQUEST CHANGES / 架构评审 WATCH）

第一轮修订稿经独立复核，结论为不可直接定版。复核确认第一轮 findings 大部分有真实代码依据，但修订稿自身存在 5 项缺陷，且第一轮有 3 处引用行号错误。全部已在本轮修正：

**修订稿自身的 5 项缺陷（全部认可，均已修）**：

1. 复制按钮范围自相矛盾——开发计划 §1「邀请链接页面增加复制按钮」与工程边界「只放后台弹窗」冲突。已统一口径：复制按钮位置为 PC 后台邀请弹窗。
2. 实施顺序冲突——自动撤销在 Phase 1、二次确认在 Phase 2，中间存在「有自动撤销、无防护」的不安全窗口。已把自动撤销移入 Phase 2 与二次确认同批交付，且二次确认先合入。
3. mock-callback 方案未真正拍板——正文「取方案 A」与末尾「尚未闭环」并存。已定版方案 A（2026-08-20），删除全部并行表述。
4. M5 把评审时的工作树快照写成当前事实。两份文档均改为规定检查动作。
5. H2 验收不完整——实测证实 FastAPI 忽略未声明的 query 参数并返回 200，仅删参数不拒绝旧 URL、OpenAPI 断言无效。改为显式拒绝逻辑 + 行为断言，新增开发计划 Phase 3.5，且因 H5 仍合法调用该参数而必须排在 Phase 3 之后。

**第一轮结论的措辞收紧（均已改）**：B1 降为「代码风险中 + 文档矛盾阻塞」；B3「不可逆」改为「token 不可恢复、可重新生成补救」；B4「无条件通过」改为「不能作为行锁语义证据」；L2 删除对执行者硬编码姓名的预设；H1 从「必须」降为「推荐 + 复用须记录理由并补负例」。

**第一轮 3 处引用行号错误（已修）**：`models.py:99`→`:102`、`status-pages-v13.js:34`→`:35`、`status-pages-v13.js:41`→`:40`。

**反向升级 1 项**：L1 由「生产现状待验证」升级为「已确认存在」——实测 `infra/nginx/default.conf` 无 `access_log` 指令、单 `location /` 全量反代，继承默认 combined 格式，raw token 进 nginx 日志是仓库配置下的确定行为。

**新增证据**：`apps/api/src/schemas/company.py:22` 状态 pattern 为 `^(ACTIVE|DISABLED|PENDING)$`，坐实 M1 的中间态场景；相关基线测试实测 10 passed，证明上述问题均属现有测试未覆盖的设计缺口。

**未采纳的复核意见 1 项**：复核认为 H4「所有 admin JS 禁止 http/https」过于宽泛。实测 `apps/admin/public/` 全部 10 个 js 文件中 `http://`/`https://` 出现次数为 0，且无 SVG xmlns 等合法字面量需求，该断言当前可落地且无误报，予以保留；但采纳配套意见——SHA-256 只能锁定改动不能证明来源可信，已要求补一次性来源审查记录（库名/版本/官方来源/审查人）。
