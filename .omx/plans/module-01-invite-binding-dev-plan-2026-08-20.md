# 第一个模块开发计划：后台专属邀请、二维码与微信确认绑定

日期：2026-08-20
状态：已修订，待开发
评审状态：架构审查意见已吸收；批判性审查通过（APPROVED）；2026-08-20 第一轮代码对照评审已吸收（第 12 节）；**同日第二轮独立复核指出的 5 项修订稿缺陷已全部修正（第 13 节），mock-callback 定版方案 A**。
配套文档：[第一个模块工作任务清单](./module-01-invite-binding-worklist-2026-08-20.md)
计划类型：高风险 deliberate 规划，认证/绑定链路优先测试先行
配套清单：`.omx/plans/module-01-invite-binding-worklist-2026-08-20.md`

## 1. 需求摘要

用户确认的第一版方案是“专属邀请及二维码确认绑定”：

- 后台对指定加盟商发出专属邀请。
- 邀请发送时必须体现“用户/负责人名称 + 公司名称”，防止发错。
- 邀请生成后提供复制按钮。**（评审修正：原文写作「邀请链接页面增加复制按钮」，"邀请链接页面"会被读作接收方 H5 落地页，与下方工程落地边界「复制按钮本轮只放在后台邀请弹窗；接收方 H5 不提供二次转发入口」直接冲突。本轮统一口径——复制按钮位置为 PC 后台的邀请弹窗，H5 侧不提供任何复制/转发专属链接的入口。）**
- 第一版先固化推荐流程，后续再逐渐完善手机号自动匹配、手动地区匹配、自行录入供应商等能力。

工程落地边界：

- 当前系统是公众号 H5 + PC 后台，不是原生微信小程序。
- 第一版不新增数据库字段，复用 `Company.owner_name` 和 `Company.name`。
- URL 只携带 token；人员/公司信息通过后端预览接口和后台接口返回。
- 不接外部发送渠道，后台只负责生成、展示、复制链接/文案/二维码。
- 复制按钮本轮只放在后台邀请弹窗；接收方 H5 不提供二次转发专属链接的入口。
- 首次绑定必须同时满足“邀请有效 + 用户显式确认 + 后端签发短时 OAuth confirmation intent”，不能只靠前端按钮文案证明已确认。

## 2. RALPLAN-DR

### Principles

1. 最小闭环优先：先把“后台邀请 -> 用户确认 -> 微信授权 -> 绑定”的主流程跑稳。
2. 身份信息不进 URL：链接只携带 token，姓名、公司、手机号不通过明文 URL 传播。
3. 绑定不可静默覆盖：已有主微信绑定时，任何新邀请都不能替换 `primary_user_id`；主账号占用必须是数据库原子操作。
4. 运营可核对可撤销：后台要能看清邀请对象、公司、有效期，并能撤销错误邀请。
5. 测试先于认证改动：OAuth、token、绑定、撤销、并发属于高风险链路，先补测试再改行为。

### Decision Drivers

1. 发错邀请的业务风险：后台必须让运营复制前看到“负责人 + 公司”。
2. 绑定错公司的数据风险：H5 必须在 OAuth 前展示公司摘要并要求确认。
3. 实现复杂度：第一版尽量复用现有 token、preview、OAuth、audit，不引入迁移和外部发送渠道。

### Options

#### Option A：复用现有公司档案字段，增强接口响应和前端确认

做法：创建邀请时返回 `company_name`、`owner_name`、`copy_text`；H5 继续用 preview 接口展示，并在用户确认后由后端签发短时 OAuth confirmation intent；绑定服务补主账号原子占用和同公司旧邀请撤销。

优点：无需迁移、与现有模型匹配，同时让“确认后绑定”成为后端可验证条件。

缺点：负责人名称使用当前公司档案，不保存发出邀请时的快照；认证接口和三个 H5 脚本都需要同步修改。

结论：推荐第一版采用。

#### Option B：新增邀请对象快照字段

做法：在 `InviteToken` 上新增 `invitee_name_snapshot`、`company_name_snapshot` 等字段，创建邀请时固化快照。

优点：历史邀请记录更准确，能解释当时发给谁。

缺点：需要迁移、回滚、历史数据填充，第一版复杂度上升。

结论：暂不采用。只有业务确认“历史快照必须不可变”后进入 P2。

#### Option C：后台直接接微信模板消息或短信发送

做法：创建邀请后自动调用微信/短信渠道发送。

优点：减少人工复制。

缺点：依赖外部资质、模板、签名、失败重试、送达状态和合规配置，不适合第一版。

结论：暂不采用。第一版人工发送。

#### Option D：把负责人和公司名称直接拼入邀请 URL

做法：在 URL query 中加入 `owner_name`、`company_name` 等可读参数。

优点：肉眼看到 URL 时容易区分。

缺点：参数可被篡改，会进入转发记录、浏览器历史和日志，也不能作为绑定依据。

结论：拒绝。姓名与公司仅通过 token 对应的后端数据展示，URL 仍保持不透明。

## 3. ADR

### Decision

第一版采用 Option A：复用现有 `Company.owner_name` 和 `Company.name`，增强后台邀请响应、后台复制/二维码 UI、H5 确认页、后端 confirmation intent、同公司唯一有效邀请和主账号原子占用；不新增数据库字段，不接外部发送渠道。

### Drivers

- 用户当前最关心发邀请时不要发错对象。
- 当前代码已经有一次性邀请 token、预览接口、OAuth start/callback 和绑定服务。
- 认证链路风险高，采用“无迁移 + 后端强约束 + 本地静态二维码库”比前端提示或外部二维码服务更可验证。

### Alternatives Considered

- 邀请快照字段：延后到 P2，等待业务确认历史不可变需求。
- 手机号自动匹配：延后，避免和专属邀请方案互相干扰。
- 自动发送渠道：延后，避免外部平台和送达状态扩大范围。
- 姓名/公司明文 URL：拒绝，防止篡改与信息泄露。

### Why Chosen

该方案复用现有 signed state、邀请 token 和公司模型，不引入持久化迁移；新增的 confirmation intent 让“负责人 + 公司 + 复制按钮 + 二维码 + 确认绑定”不仅是页面文案，也是后端可验证条件。

### Consequences

- 如果后台修改了公司负责人，旧邀请预览会显示当前负责人，而不是生成时负责人。
- 生成同公司新邀请会撤销旧有效邀请；旧链接保持失效，回滚代码也不会自动恢复旧链接。
- 本地 vendored 二维码库需要固定版本、许可证文件和静态自包含测试。
- 生产上线仍依赖真实服务号网页授权域名和 AppID 配置验收。

### Follow-ups

- P1 补邀请记录与历史使用者追溯。
- P2 再评估邀请快照、手机号自动匹配、外部发送渠道。

## 4. 开发阶段

### Phase -1：实施基线与分支隔离

- 当前仓库可能同时存在其他 V1.2 整改工作；实施前先运行 `git rev-parse --show-toplevel` 和 `git status --short --branch`，确认真实嵌套仓库与未提交改动。
- **（评审修正 M5，二次核查后改写）** 本条原先写死了 2026-08-20 评审当时的 `git status` 快照（列举了 8 个具体文件），但工作树在评审期间已经变化，快照迅速失效并会误导执行者。**改为规定检查动作而非检查结果**：
  1. 开工时实际运行 `git status --short --branch`，不要采信本文档或任何历史快照中的文件清单。
  2. 若工作树非干净，先把改动提交或 stash 到位，再切分支——不要在脏工作树上开始本模块。
  3. 用 `git diff --name-only` 与本模块目标文件（`apps/admin/public/app.js`、`apps/api/tests/test_frontend_contract.py`、`apps/api/src/routers/auth.py`、`apps/api/src/services/auth_service.py`、`apps/h5/public/*.js`）取交集，**有交集才需要处理冲突，没有交集就直接切分支**。
  已知事实（不随时间失效的部分）：该仓库长期存在并行的 V1.2 整改工作，分支 `fix/v12-remediation-closure` 上会不定期出现未提交改动，因此这一步检查每次开工都要做。
- 非平凡功能使用 `feat/invite-binding-confirmation` 分支或隔离 worktree，不覆盖其他人对 `apps/admin/public/app.js`、前端合同测试或 OAuth 文件的修改。
- 本模块按“测试 -> 后端 -> 后台 -> H5 -> PostgreSQL/浏览器验证”拆成可独立回滚的中文 Lore commits；计划文档本身不授权修改生产配置、微信 AppSecret 或外部平台。

### Phase 0：行为锁定与现状保护

预计改动文件：

- `apps/api/tests/test_auth_company.py`
- `apps/api/tests/test_pre_go_live_security.py`
- `apps/api/tests/test_invite_preview.py`
- `apps/api/tests/test_frontend_contract.py`
- `apps/api/tests/test_wechat_oauth.py`
- `apps/api/tests/test_pre_go_live_security_review.py`
- `apps/api/tests/test_invite_binding_postgres_concurrency_e2e.py`
- `scripts/run_v12_e2e.py`

步骤：

1. 新增失败测试：创建邀请响应包含 `company_name`、`owner_name`、`copy_text`，且 URL 不包含明文姓名/公司。
2. 新增失败测试：同公司已绑定主用户后，另一个 openid 使用新邀请不能覆盖 `primary_user_id`。
3. 新增失败测试：同公司两条不同 token 被两个 openid 并发使用时，只能产生一个主账号、一个新用户和一个微信身份；PostgreSQL 专项测试加入 `scripts/run_v12_e2e.py` 的 `TARGET_TESTS`。
4. 新增失败测试：生成同公司新邀请后，旧有效邀请自动失效；并发生成完成后最多一条邀请有效。**（评审修正 B4，二次核查后收紧措辞：并发生成部分必须写入 `test_invite_binding_postgres_concurrency_e2e.py` 并纳入 `TARGET_TESTS`。该验收依赖 `SELECT ... FOR UPDATE`，而 `with_for_update()` 在 SQLite 上是 no-op——准确说法是「SQLite 下的通过不能作为行锁语义的证据」，而非「一定会无条件通过」：SQLite 自身有库级写锁，可能意外串行化而假绿，也可能因锁竞争而报 database is locked 假红，两种结果都无参考价值。「旧邀请自动失效」的串行部分可留在 SQLite。）**
5. 新增失败测试：未经确认、伪造或过期 confirmation intent 不能完成首次绑定。
6. 新增失败测试：后台静态文件包含复制按钮、降级复制逻辑、本地二维码库和二维码容器。
7. 新增失败测试：`app.js`、`enhancements.js`、`status-pages-v13.js` 不再存在可绕过确认的独立 OAuth 跳转路径。**（评审修正 H3：断言形式必须可机器判定——三个脚本中对 `#wechat-login` 的 `onclick` 赋值与 `addEventListener` 注册合计只出现一处。当前 `enhancements.js:64-75` 是直接赋值覆盖、`status-pages-v13.js:35` 是包装原 handler，两者都挂 `MutationObserver` 到 `document.documentElement`，勾选门禁能生效仅因 `apps/h5/public/index.html:29` 先于 `:39` 加载。）**
8. **（评审新增 B1）** 新增失败测试：`wechat_dev_mock=True` 时，不带 confirmation intent 的 `POST /auth/wechat/mock-callback` 被拒绝。
9. **（评审修正 H2，二次核查后改写）** 新增失败测试：`GET /auth/wechat/start?invite=<任意值>` 返回 400 且错误码为 `AUTH_INVITE_ENTRY_DEPRECATED`。**不能只断言 OpenAPI 中参数消失**——实测 FastAPI 忽略未声明 query 参数并返回 200，schema 断言无法证明旧 URL 被拒。schema 检查可作辅助项。
10. **（评审新增 H4）** 新增失败测试：`apps/admin/public/` 下所有 `*.js` 全文不含 `http://` / `https://`；`vendor/qrcode.min.js` 存在且 SHA-256 等于记录值。
11. **（评审新增 M2）** 新增失败测试：主账号占用失败后，该公司的 `User` 与 `WechatIdentity` 计数各为 1（锁定隐式回滚行为）。
12. **（评审新增 M1）** 新增失败测试：非 `ACTIVE` 且非 `DISABLED` 状态的公司不能创建邀请。
13. **（评审新增 B3）** 新增失败测试：后台「邀请」按钮的直接 onclick 中不发出创建请求，存在二次确认步骤。

验收：

- 新增测试在当前代码上至少部分红灯，能证明缺口。
- 现有 `test_oauth_state_redirect_invite_replay_and_cross_company_binding_are_rejected` 保持覆盖。
- **（评审补充）** 步骤 4 的并发部分与步骤 3 同处 PostgreSQL 专项文件；红灯证据须来自 `scripts/run_v12_e2e.py` 的实际执行，skip 不算红灯也不算绿灯。

### Phase 1：后端邀请响应与绑定保护

预计改动文件：

- `apps/api/src/services/auth_service.py`
- `apps/api/src/routers/auth.py`
- `apps/api/src/schemas/auth.py`
- `apps/api/src/routers/invite_preview.py`

步骤：

1. `create_company_invite` 或 router 层组装安全展示信息，返回 `company_name`、`owner_name`、`copy_text`。**（评审补充 L2：`owner_name` 可为空，`copy_text` 必须有降级分支，不得硬编码示例姓名。）**
2. 创建邀请时锁定目标公司；公司已有主账号则拒绝创建。**（评审补充 M1：同时把公司状态判定从 `status == "DISABLED"` 统一为 `status != "ACTIVE"`，与预览/绑定路径对齐。实测 `apps/api/src/schemas/company.py:22` 的 pattern 为 `^(ACTIVE|DISABLED|PENDING)$`，`PENDING` 就是那个能创建出必然预览失败邀请的中间态。）** **（评审修正，实施顺序 B3：「撤销同公司旧有效邀请」已从本阶段移出，改到 Phase 2 与后台二次确认同批交付——见 Phase 2 说明。）**
3. 新增 `POST /api/v1/auth/invites/confirm-start`：请求 `{"invite":"<raw-token>","return_url":"/h5/#/home"}`；校验邀请与 return URL 后返回 `{"authorization_url":"<wechat-oauth-url>","expires_at":"<iso-time>"}`。
4. confirmation signed state 采用现有 `create_signed_state`，只包含 `invite_id`、`company_id`、`binding_confirmed=true`、`return_url`，不包含 raw invite token、复制文案或 AppSecret。**（评审建议 H1，二次核查后收紧措辞：这是纵深防御加固，不是唯一正确解。复用 `purpose="wechat-oauth"` 并在 callback 严格校验 `binding_confirmed is True` 同样可以安全实现。本计划推荐用独立值 `wechat-oauth-bind`，理由是 `purpose` 是 `decode_signed_state` 唯一的类型校验（`core/security.py:158-163`），用它分流能让"旧 state 冒充确认 state"在 decode 阶段就失败，而不依赖调用方记得写严格的 `is True` 判定。若执行者选择复用方案，必须在 PR 说明中写明理由，并补一条"payload 缺少 `binding_confirmed` 时拒绝"的负例测试。有效期沿用 `expires_minutes` 默认值 10（`core/security.py:147`），不传该参数。）**
5. **（评审改写 B2 + H2）** 重构邀请消费路径：`_consume_invite` 与 `_validate_invite` 增加按 `invite_id` 查找的入口，条件更新的 `where` 从 `token_hash ==` 改为 `id ==`，**`used_at IS NULL`、`revoked_at IS NULL`、`expires_at > now` 三个条件原样保留**（一次性消费的并发边界，不得弱化）。`login_or_bind_wechat` 相应接受 `invite_id`。callback 按 state 的 `purpose` 分流：`wechat-oauth-bind` 才允许首次绑定，legacy `wechat-oauth` 只允许已绑定登录。
6. **（评审新增 B1，方案 A 已定版）** 处置 `POST /auth/wechat/mock-callback`：该接口经 `bind_wechat_by_invite` 直达 `login_or_bind_wechat`，不经过任何 signed state（`routers/auth.py:176-186`），而 `wechat_dev_mock` 默认为 `True`（`core/config.py:42`）。**决议：采用方案 A——mock-callback 同样要求携带后端签发的 confirmation intent**，使开发/测试/预发环境的绑定合同与生产一致。本项已拍板，执行者不得自行改用其他方案。
   注：`apps/api/src/core/production.py:67` 会把 `wechat_dev_mock=True` 列为生产启动阻断错误，因此这**不是现存生产绕过漏洞**，代码风险等级为「中」；升为阻塞的是文档层面的自相矛盾（§6 曾把 mock callback 当作正向绑定用例，与 P0-04 验收字面冲突），该矛盾已在本轮修订中消除。
7. **（评审修正 H2，二次核查后改写）** `/auth/wechat/start` 的 `invite` 参数处置**不在本阶段执行**，已移至 Phase 3.5——因为 H5 当前仍在合法调用该参数（`apps/h5/public/app.js:39`、`apps/h5/public/enhancements.js:74`），在 Phase 3 完成前删除会直接打断现网登录。
8. `login_or_bind_wechat` 使用数据库条件更新原子占用 `primary_user_id`；若占用失败，整笔事务回滚，不残留用户、角色、微信身份或已消费邀请。**（评审补充 M2：该回滚是隐式的，由 `get_db` 的 `session.close()` 提供（`core/database.py:34-39`），无全局 `AppError` → rollback 处理器。实现时在代码注释中标注这一依赖，并由 Phase 0 步骤 11 的计数断言守住。）**
9. 对已存在 identity 且同公司登录的场景保持幂等，不造成跨公司或覆盖。
10. 错误码使用可映射的明确冲突码，例如 `AUTH_COMPANY_ALREADY_BOUND`、`AUTH_BINDING_CONFIRM_REQUIRED`。

验收：

- 认证单测和安全负例通过。
- 不记录原始 token 到 audit；audit 仍只记录 invite id/user/company。
- 两个不同 token 的同公司并发测试在 PostgreSQL 集成环境下通过，不能只用单 token 测试替代。
- **（评审补充）** 并发**创建**邀请的测试同样在 PostgreSQL 下通过。
- **（评审补充 B1）** 无 confirmation intent 的 mock-callback 被拒绝。
- **（评审补充 M1）** `PENDING` 状态公司无法创建邀请。
- 没有数据库迁移。
- **（评审补充，实施顺序 B3）** 本阶段交付后系统仍处于安全可交付状态：未引入自动撤销，误发邀请不会作废他人有效链接。

### Phase 2：后台二次确认、旧邀请自动撤销与邀请弹窗增强

**（评审改写，实施顺序 B3）** 本阶段名称与范围经评审调整：原计划把「自动撤销同公司旧有效邀请」放在 Phase 1、把防误操作的二次确认放在 Phase 2，导致两阶段之间存在一个「有自动撤销、无误操作防护」的窗口，违反「每个增量保持安全可交付」原则。现将二者**合并到本阶段同批交付**，且二次确认（步骤 1）必须先于自动撤销（步骤 2）合入。

预计改动文件：

- `apps/admin/public/app.js`
- `apps/admin/public/index.html`
- `apps/admin/public/styles.css`
- `apps/admin/public/vendor/qrcode.min.js`
- `apps/admin/public/vendor/QR-LICENSE.txt`
- `apps/api/src/services/auth_service.py`（自动撤销，自 Phase 1 移入）
- `apps/api/tests/test_auth_company.py`
- `apps/api/tests/test_frontend_contract.py`

步骤：

1. **（评审新增 B3，对应 P0-08）** 点击「邀请」先弹二次确认，展示「将为【公司名称】的负责人【负责人姓名】生成新的绑定邀请」；该公司已有有效邀请时追加提示「生成后原邀请将立即失效」。确认后才发起创建请求。**必须先于步骤 2 合入。**
2. **（自 Phase 1 移入）** 对未绑定公司生成新邀请时，在同一事务内撤销该公司其他未使用、未过期、未撤销的邀请，再创建新邀请；旧链接统一返回邀请失效，不泄露被哪条新邀请替换。
3. 邀请接口返回后，弹窗展示负责人、公司、有效期。
4. textarea 默认放完整邀请文案。
5. 增加“复制完整邀请文案”“复制链接”按钮，成功/失败 toast。
6. 增加“撤销本次邀请”按钮，发现发错时立即使链接失效。
7. 使用固定版本、带许可证文件的本地 vendored 二维码 JS 库渲染邀请 URL；不使用 CDN、在线二维码服务或手写编码算法。
8. 二维码渲染失败时显示错误提示，但复制完整文案和纯链接仍可用。
9. **（评审新增 H4）** 将 vendor 文件的 SHA-256 记录到 `apps/api/tests/test_frontend_contract.py` 的常量中，并在文档或 `QR-LICENSE.txt` 中注明库名、版本、来源与哈希。

验收：

- 后台静态合同测试通过。
- `index.html` 不新增外部 `http/https` 资源。
- **（评审补充 H4）** `apps/admin/public/` 下所有 `*.js` 全文不含 `http://` / `https://`。现有自包含测试只扫 `index.html` 的 `src`/`href`（`apps/api/tests/test_frontend_contract.py:27-38`），发现不了 js 里动态 `createElement('script'); s.src='https://…'` 的注入，必须由新增测试覆盖。
- vendor 文件、许可证和版本说明存在 **且 SHA-256 与记录值一致**，二维码实际编码值等于接口返回 `url`。
- **（评审补充 B3）** 创建邀请的请求不在「邀请」按钮的直接 onclick 中发出；取消确认不产生 `INVITE_CREATE` 审计记录。
- 操作路径不需要运营手动选择 textarea 才能复制。

### Phase 3：H5 邀请确认体验

预计改动文件：

- `apps/h5/public/app.js`
- `apps/h5/public/enhancements.js`
- `apps/h5/public/status-pages-v13.js`
- `apps/h5/public/status-pages-v13.css`
- `apps/api/tests/test_frontend_contract.py`

步骤：

1. 基础登录文案改为“确认公司信息后授权绑定”。
2. 邀请预览卡增加清楚标题：`请确认是否绑定到【公司名】`，展示负责人、公司、地区和有效期。
3. 将三个脚本对 `#wechat-login` 的处理收敛为唯一函数；MutationObserver 不得覆盖确认门禁。**（评审补充 H3：具体做法是把事件绑定从 `enhancements.js:64-75` 和 `status-pages-v13.js:35` 全部摘掉，只在一处注册。当前 `enhancements.js` 用的是直接赋值覆盖而非包装，勾选门禁能生效仅因 `index.html:29` 先于 `:39` 加载——这是靠 script 标签顺序撑住的隐式契约，必须消除。改造时保留 `status-pages-v13.js:40` 预览失败时 `btn.disabled=true` 的现有行为。）**
4. 授权按钮只有在邀请预览成功、用户勾选规则并明确确认后，才调用后端确认接口取得微信授权 URL。
5. 邀请失效、公司停用、公司已有主账号或确认 intent 失效时禁用按钮并展示处理建议。
6. **（评审新增 H2）** 清理三个脚本中拼接 `/auth/wechat/start?invite=` 的代码（`apps/h5/public/app.js:39`、`apps/h5/public/enhancements.js:69-74`），改走 `POST /auth/invites/confirm-start`。
7. **（评审补充）** 确认卡的有效期直接用 preview 已返回的 `expires_at`（`apps/api/src/routers/invite_preview.py:39`），无需新增字段或接口。

验收：

- H5 无“自动绑定”文案。
- 邀请预览失败不会发起 OAuth。
- 直接调用旧 `/auth/wechat/start?invite=...` 不能完成首次绑定。**（评审修正 H2：该参数已被移除，本条应表述为「该 URL 形式已不被接受」。）**
- **（评审修正 H3）** 静态合同测试断言：三个脚本中对 `#wechat-login` 的 onclick 赋值与 addEventListener 注册合计只出现一处。原表述「只有一个受确认门禁保护的 OAuth 入口」不可机器判定，浏览器测试作为补充证据而非唯一证据。
- 浏览器测试证明页面多次 MutationObserver patch 后仍只有一个受确认门禁保护的 OAuth 入口。

### Phase 3.5：停用 `/wechat/start` 的 invite 入口（评审新增，H2）

**必须排在 Phase 3 之后**：H5 当前仍在合法调用 `/auth/wechat/start?invite=`（`apps/h5/public/app.js:39`、`apps/h5/public/enhancements.js:74`），在 Phase 3 把入口切到 confirm-start 之前执行本阶段会直接打断现网登录。因此 H2 的准确表述是「confirm-start 落地后该参数不再需要」，而不是「已无合法调用方」。

预计改动文件：

- `apps/api/src/routers/auth.py`
- `apps/api/tests/test_wechat_oauth.py`

步骤：

1. 移除 `/auth/wechat/start` 函数签名中的 `invite` 参数及其邀请校验分支（`apps/api/src/routers/auth.py:188-210`）。
2. **增加显式拒绝逻辑**：从 `request.query_params` 检测到 `invite` 键时返回 400、错误码 `AUTH_INVITE_ENTRY_DEPRECATED`，文案提示「请从最新邀请链接重新进入」。

步骤 2 不可省略。实测确认 FastAPI 对未声明的 query 参数**直接忽略并返回 200**（`GET /start?invite=<raw>` → `200`，参数被丢弃），只删签名不会拒绝旧 URL，只会让旧链接静默走完一次微信跳转、最后在 callback 因 `invite_token=None` 报「未绑定」。**这不构成安全漏洞**——首次绑定仍然失败——但用户看到的是「授权失败」而非「链接已过期」，属于可诊断性与合同清晰度问题。

验收：

- `GET /auth/wechat/start?invite=<任意值>` 返回 400 且错误码为 `AUTH_INVITE_ENTRY_DEPRECATED`。**这是本阶段唯一有效验收**；「OpenAPI 中参数消失」只能作为辅助断言，不能单独证明旧 URL 被拒。
- 无邀请的已绑定用户登录路径不受影响。

### Phase 4：P1 邀请记录与历史追溯

预计改动文件：

- `apps/api/src/routers/auth.py`
- `apps/api/src/services/auth_service.py`
- `apps/admin/public/app.js`
- `apps/api/tests/test_auth_company.py`

步骤：

1. 补公司邀请记录查询接口，按创建时间倒序返回状态。
2. 后台展示最近邀请记录和撤销按钮。
3. 展示可证实的使用时间和当前主账号；没有历史快照时明确标记“未记录”，不反推伪造历史使用者。
4. **（评审新增 M4）** 修复 `revoke_invite` 的静默成功：`apps/api/src/routers/auth.py:161-173` 的 `if invite:` 没有 else 分支，对不存在的 invite 也返回「邀请已撤销」。把撤销按钮暴露给运营后，撤销失败会被显示为成功。改为返回 404，或响应体带 `revoked: true/false`。

验收：

- 已撤销邀请 preview/start/callback 均失败。
- 运营能看到邀请状态并撤销未使用邀请；P0 已保证同公司最多一条有效邀请。
- **（评审补充 M4）** 撤销不存在的 invite_id 返回明确失败，前端不显示成功提示。

### Phase 5：回归、打包与上线前验证

预计命令：

- `uv run pytest apps/api/tests/test_auth_company.py apps/api/tests/test_invite_preview.py apps/api/tests/test_pre_go_live_security.py apps/api/tests/test_pre_go_live_security_review.py apps/api/tests/test_frontend_contract.py`
- `uv run pytest apps/api/tests/test_wechat_oauth.py`
- `uv run python scripts/run_v12_e2e.py`：启动或连接名称含 `e2e/test/ci` 的隔离 PostgreSQL，必须实际执行新增 `test_invite_binding_postgres_concurrency_e2e.py`；若因 Docker/数据库缺失而跳过，不得宣称并发验收通过。
- 如仓库当前验证规范要求，再运行完整相关 API 测试集。

验收：

- 目标测试通过。
- `scripts/run_v12_e2e.py` 的 JUnit/退出码证明 PostgreSQL 邀请并发测试实际执行而非 skip。
- 安全扫描确认改动中没有 token、AppSecret、手机号明文日志。
- Chromium 后台测试验证复制成功/降级、二维码编码值、撤销；移动端 H5 测试验证 preview/确认/MutationObserver 门禁。
- 生产验收单独复测真实服务号 OAuth，不用本地 mock 代替。

## 5. Pre-mortem

### Failure 1：增强脚本覆盖确认按钮，用户未核对公司就进入 OAuth

预防：

- 三个 H5 脚本共享唯一 OAuth 入口。
- preview 成功、规则同意、用户确认缺一不可。
- 后端 signed confirmation intent 阻止直接构造 start URL 绕过。
- **（评审补充 H3）** 该失败当前已实际存在于代码中，只是被 script 加载顺序掩盖：`enhancements.js:64-75` 对 `#wechat-login` 是直接赋值覆盖而非包装，勾选门禁能生效仅因 `index.html:29` 先于 `:39`。因此预防措施不能只靠「共享唯一入口」的约定，必须由静态合同测试对事件绑定处数计数守住，否则任何加载顺序调整都会让门禁静默消失且测试全绿。
- **（评审补充 H2）** 彻底做法是移除 `/wechat/start` 的 `invite` 参数，使绕过路径在结构上不存在，而非依赖 callback 里的防守分支。

### Failure 2：同公司不同 token 并发导致后绑定者覆盖主账号

预防：

- 创建新邀请时锁定公司并撤销旧有效邀请。
- 主账号通过 `primary_user_id IS NULL` 条件更新原子占用。
- 以 PostgreSQL 并发测试验证失败事务不残留用户、角色或身份。

### Failure 3：二维码实现将一次性 token 发送到第三方或生产静态资源缺失

预防：

- 固定使用本地 vendored、带许可证的版本，不使用在线二维码服务。
- 静态引用存在性测试覆盖 vendor 文件和许可证。
- **（评审补充 H4）** 存在性测试挡不住供应链投毒，必须升级为 SHA-256 完整性校验；同时现有自包含测试只扫 `index.html` 的 `src`/`href`（`apps/api/tests/test_frontend_contract.py:27-38`），发现不了 js 内动态注入的 CDN `script.src`，需补 admin js 全文外链扫描。缺这两项时本 Failure 的预防措施实际不成立。
- 二维码失败不阻塞复制链接。

## 6. 测试计划

### Unit

- `create_company_invite` 返回安全展示信息；`owner_name` 为空时 `copy_text` 走降级文案。
- 生成新邀请会撤销同公司旧有效邀请，并拒绝已绑定公司；非 `ACTIVE` 公司拒绝创建。
- confirmation intent 只能由有效邀请签发，且篡改/过期失败；**`purpose` 不为 `wechat-oauth-bind` 时 decode 阶段即拒绝**。
- `login_or_bind_wechat` 拒绝覆盖已有主账号；占用失败后 `User` / `WechatIdentity` 计数各为 1。
- **（评审修正 B2）** `_consume_invite` 改为按 `invite_id` 消费后，仍保持一次性语义：`used_at IS NULL`、`revoked_at IS NULL`、`expires_at > now` 三个条件不变。原表述「继续保持一次性消费」易被理解为该函数不需改动，与 Phase 1 步骤 5 的改造要求矛盾，此处已澄清。

### Integration

- **（评审修正 B1）** 创建邀请 -> preview -> **confirm-start 取得 intent** -> mock callback -> 绑定成功。原用例为「创建邀请 -> preview -> mock callback -> 绑定成功」，它把一条不经过 confirmation intent 的绑定路径确立为正向行为，与 worklist P0-04 验收「新微信只有携带 confirmation intent 才能完成绑定」直接冲突，已按 Phase 1 步骤 6 的方案 A 改写。
- **（评审新增 B1）** `wechat_dev_mock=True` 时，不带 intent 的 mock callback -> 拒绝。
- preview -> 明确确认 -> signed intent -> OAuth callback -> 绑定成功。
- 未确认/伪造/过期 intent -> callback 不绑定。
- 创建邀请 -> 撤销 -> preview/start/callback 均失败。
- 已绑定公司 -> 新 openid 使用新邀请 -> 返回绑定冲突。
- 同公司不同 token/不同 openid 并发 -> 仅一个绑定成功且无孤儿账号。
- 同 openid 同公司重复登录 -> 不创建第二个主账号。

### E2E / Contract

- **（评审新增 B3）** 后台公司页点击邀请先出二次确认，取消不创建 token。
- 后台公司页点击邀请，弹窗含负责人、公司、复制完整文案、复制链接、二维码区域。
- **（评审新增 H3/H4）** 静态合同：三个 H5 脚本对 `#wechat-login` 的事件绑定合计一处；admin js 全文无外链；vendor SHA-256 一致。
- 后台真实复制/降级复制均可用，二维码扫码结果与链接完全一致，撤销后二维码链接失效。
- H5 invite link 打开后展示公司摘要；多次增强层 patch 后仍必须确认才能取得 OAuth URL。
- 无邀请、失效邀请、公司停用均不允许进入 OAuth。

### Observability

- audit 保留 `INVITE_CREATE`、`INVITE_REVOKE`、`WECHAT_OAUTH_LOGIN`/`WECHAT_BIND`。
- 自动撤销旧邀请记录原因和 invite id，但不记录原始 token、包含 token 的 `copy_text` 或 authorization URL。
- 认证失败日志只记录错误码、company_id/invite_id/request_id 等安全上下文，不记录原始 token、授权 URL、AppSecret 或手机号。
- 生产 OAuth 验收单独记录 AppID、授权域名、callback、用户持久化、角色权限结果，但不记录 AppSecret。
- **（评审新增 L1，二次核查后升级为「已确认存在」，不再是「待验证」）** 实测 `infra/nginx/default.conf` 全文只有一个 `location /` 全量反代，**没有任何 `access_log` 指令**，即继承 nginx 默认的 combined 格式，而 combined 的 `$request` 字段包含完整 URI 与 query string。因此 `GET /auth/invites/preview?invite=<raw-token>` 在当前仓库配置下**是确定会被写入 nginx access log 的**，不是假设。应用层 `uvicorn.access` 虽已 `disabled = True`（`apps/api/src/core/logging.py:48-51`），挡不住这一层。
  整改项（任选其一，须落地并留证）：① 在 `infra/nginx/default.conf` 为 API 路径设置不含 `$query_string` 的自定义 `log_format`，或对 `/api/v1/auth/invites/` 前缀 `access_log off`；② 把 preview 也改为 POST，token 走请求体。
  另需复测生产实际使用的宝塔 nginx 配置是否覆盖了仓库内配置——仓库配置本身已构成确定的泄露路径，生产是否更糟或更好需单独确认。

## 7. 回滚策略

- Phase 1 后端改动可通过回滚 commit 恢复旧邀请响应和绑定行为；无迁移，回滚成本低。
- Phase 2/3 前端改动可单独回滚静态文件，后端增强响应仍兼容旧前端。
- P0 自动撤销产生的旧邀请不会因代码回滚自动恢复；这是安全优先的预期结果，必要时只能重新生成新邀请，禁止手工清空 `revoked_at` 恢复旧 token。
- 本地二维码 vendor 文件可随前端 commit 回滚；回滚后后台仍保留复制链接能力。
- 若生产 OAuth 配置失败，不回滚代码；应按配置问题处理，因为本模块代码仍可在 mock/测试环境验证。

## 8. 估算与复杂度

复杂度：HIGH。原因是 UI 改动不大，但涉及后端可验证确认、一次性 token、不同 token 并发、主账号原子占用和生产 OAuth 验收边界。

建议拆分（**评审修正 L3：原估算合计 4-6.5 天偏乐观，Phase 0 与 Phase 1 已上调**）：

- Phase 0 红灯测试与并发夹具：**1-1.5 天**（原 0.5-1 天）。理由：评审后 Phase 0 从 7 步增至 13 步，且仓库内仅 `apps/api/tests/test_internal_user_postgres_concurrency_e2e.py` 一个可参考夹具，PostgreSQL 并发夹具要同时覆盖「绑定并发」与「创建并发」两类场景。
- P0 后端 confirmation intent、唯一有效邀请、原子占用：**1.5-2 天**（原 1-1.5 天）。理由：新增 `_consume_invite` 按 invite_id 改造、移除 start 的 invite 参数、mock-callback 处置三项工作。
- P0 后台二次确认、旧邀请自动撤销（自 Phase 1 移入，二轮调整）、复制/本地二维码/撤销：1-1.5 天。
- P0 H5 三脚本确认链路：0.5-1 天。
- Phase 3.5 停用 invite 入口（二轮新增）：0.5 天。
- P1 邀请记录与历史追溯：0.5-1 天。
- 回归与上线前验证：0.5-1 天；不含微信平台外部审批等待。
- **合计：5.5-8 天**，不含 Phase -1 基线检查与整理时间。

## 9. 执行交接建议

推荐执行顺序：

1. `test-engineer` 先写 Phase 0 红灯测试和 PostgreSQL 并发夹具。
2. `executor` 做 Phase 1 后端，保持无迁移；认证实现低于高置信时必须提交安全人工复核。
3. 两个 `executor` 可分别做后台 UI 与 H5 UI，但 `apps/api/tests/test_frontend_contract.py` 由测试负责人统一维护，避免冲突。
4. `code-reviewer` 专门审查 confirmation intent、token 日志、事务回滚和二维码供应链。**（评审补充：额外必查四项——signed state 的 `purpose` 是否已分流、`/wechat/start` 的 `invite` 参数是否已删干净、mock-callback 是否已按选定方案处置、`_consume_invite` 改 invite_id 后三个并发边界条件是否原样保留。）**
5. `verifier` 跑目标测试、全量相关回归、安全扫描和真实浏览器 smoke。**（评审补充：必须核对 `scripts/run_v12_e2e.py` 的 JUnit 输出，确认两类 PostgreSQL 并发测试——绑定并发与创建并发——均为实际执行而非 skip。）**

## 10. 本轮不做

- 不做微信手机号授权和手机号自动匹配。
- 不做地区手动选择供应商。
- 不做供应商自行录入/申请匹配。
- 不做外部短信/微信模板消息自动发送。
- 不新增邀请快照字段或迁移，除非业务确认 P2 需求。

## 11. 计划变更记录

- 2026-08-20：基于当前仓库邀请/OAuth/后台/H5 实现证据生成第一版任务清单和开发计划。
- 2026-08-20：架构审查后增加后端 signed confirmation intent、三个 H5 脚本单一入口、同公司旧邀请 P0 自动撤销、主账号原子占用、固定本地二维码 vendor 路径和 PostgreSQL 并发验收。
- 2026-08-20：批判性审查通过；补充确认接口的精确请求/响应契约，以及 PostgreSQL 并发测试必须由 `scripts/run_v12_e2e.py` 实际执行且不得以 skip 作为通过证据。
- 2026-08-20：**代码对照文档评审**（详见配套清单第 8 节「评审备注」）。核对初版全部代码引用，确认基本准确（两处偏差已修正）。新增 4 项阻塞级修改：mock-callback 绕过路径处置（B1）、`_consume_invite` 按 invite_id 改造（B2）、二次确认自 P1-03 上提为 P0-08（B3）、并发创建邀请验收指定 PostgreSQL（B4）；4 项高优先级修改：confirmation intent 独立 purpose（H1）、移除 `/wechat/start` 的 invite 参数（H2）、H5 事件绑定验收改为可 grep 计数（H3）、admin js 全文外链扫描 + vendor SHA-256（H4）；另有 M1-M5、L1-L3 共 8 项一致性与低优先级修改。估算由 4-6.5 天上调至 5-7.5 天。
- 2026-08-20（第二轮）：**独立复核（代码评审 REQUEST CHANGES / 架构评审 WATCH）**，修正修订稿自身 5 项缺陷并收紧措辞（详见第 13 节）：① 复制按钮口径统一为后台弹窗；② 旧邀请自动撤销自 Phase 1 移入 Phase 2、与二次确认同批交付且二次确认先合入；③ mock-callback 定版方案 A；④ M5 快照改为检查动作；⑤ H2 实测证伪「删参数即拒绝」（FastAPI 忽略未声明 query 参数返回 200），新增 Phase 3.5 显式拒绝 + 行为断言。另：修正 3 处引用行号，B1/B3/B4/L2/H1 措辞收紧，L1 升级为已确认（nginx 无 `access_log` 指令），估算调整为 5.5-8 天。

## 12. 评审备注（2026-08-20 代码对照评审，第一轮）

**（二轮说明：下表记录第一轮改动的原始去向；其中涉及的步骤编号与阶段归属已被第 13 节的修订调整——自动撤销移入 Phase 2、`/wechat/start` invite 参数处置移入 Phase 3.5、mock-callback 定版方案 A。以当前正文为准。）**

本节独立记录本次评审对本文档的改动，正文中所有由评审引入的内容均以 **（评审补充 / 评审修正 / 评审改写 / 评审新增）** 标记，可与初版区分。完整问题清单、级别与证据见配套清单 `module-01-invite-binding-worklist-2026-08-20.md` 第 8 节。

本文档受影响的章节：

| 章节 | 改动 | 对应编号 |
|---|---|---|
| Phase -1 | 写死分支基线前置条件（当前 `fix/v12-remediation-closure` 有 8 个未提交改动，与本模块目标文件重叠） | M5 |
| Phase 0 | 步骤 4 并发部分指定 PostgreSQL；步骤 7 改为可 grep 计数；新增步骤 8-13 | B4 / H3 / B1 / H2 / H4 / M1 / M2 / B3 |
| Phase 1 | 步骤 4 改独立 purpose；步骤 5 改写为消费路径重构 + 移除 start 的 invite 参数；新增步骤 6 处置 mock-callback；步骤 7 标注隐式回滚依赖 | H1 / B2 / H2 / B1 / M2 / M1 / L2 |
| Phase 2 | 新增步骤 0（二次确认，须先于其他步骤）与步骤 7（SHA-256 记录）；验收补 admin js 全文外链扫描 | B3 / H4 |
| Phase 3 | 步骤 3 补明 `enhancements.js` 是覆盖者及 script 顺序依赖；新增步骤 6-7；验收改为可机器判定 | H3 / H2 |
| Phase 4 | 新增步骤 4 修复 `revoke_invite` 静默成功 | M4 |
| §6 测试计划 | 改写 Integration 首条 mock callback 用例；澄清 `_consume_invite` 表述；补 E2E/Contract 与 Observability 条目 | B1 / B2 / B3 / H3 / H4 / L1 |
| §8 估算 | Phase 0 与 Phase 1 上调，合计 5-7.5 天 | L3 |

**决议记录**：Phase 1 步骤 6 的 mock-callback 处置**已拍板取方案 A**（mock-callback 同样要求 confirmation intent），2026-08-20 确认。本文档与配套清单中的相关条目均已按方案 A 统一，不再保留"或方案 B"的并行表述。执行者不得自行改用其他方案；如需变更，须走计划变更流程并同步修改本文档 Phase 1 步骤 6、§6 Integration 两条、配套清单 P0-04 任务与验收各一条。

## 13. 第二轮评审备注（2026-08-20，独立代码评审 + 架构评审）

第一轮评审结论经独立复核，代码评审 `REQUEST CHANGES`、架构评审 `WATCH`。复核确认第一轮findings大部分有真实代码依据，但**第一轮修订稿自身引入了新缺陷**，本轮已全部修正。

**修订稿被查出的 5 个问题（全部认可并已修）**：

| # | 问题 | 处置 |
|---|---|---|
| 1 | 复制按钮范围自相矛盾：§1 写「邀请链接页面增加」，工程边界写「只放后台弹窗」 | §1 已统一口径，明确为 PC 后台弹窗 |
| 2 | 实施顺序冲突：自动撤销在 Phase 1、防误操作的二次确认在 Phase 2，中间存在不安全窗口 | 自动撤销移入 Phase 2，与二次确认同批交付，且二次确认先于自动撤销合入 |
| 3 | mock-callback 方案未真正拍板：正文写「取方案 A」，末尾写「尚未闭环」 | 已定版方案 A，删除并行表述 |
| 4 | M5 把评审时的工作树快照写成当前事实 | 改为规定检查动作而非检查结果 |
| 5 | H2 验收不完整：移除 FastAPI 参数声明不会拒绝旧 URL | **实测证实**：未声明 query 参数返回 200 被忽略。新增 Phase 3.5，要求显式拒绝逻辑 + 行为断言验收 |

**第一轮结论的措辞收紧（4 项）**：

- **B1 分级**：`production.py:67` 把 `wechat_dev_mock=True` 列为生产启动阻断错误，故**不是现存生产绕过漏洞**。代码风险降为「中」，阻塞级的是文档自相矛盾。
- **B3「不可逆」**：改为「该 token 不可恢复，但可重新生成邀请补救」，业务上可恢复。
- **B4「无条件通过」**：改为「SQLite 下的通过不能作为行锁语义证据」，避免绝对化。
- **L2**：原文已写"例如"，"执行者会硬编码张老板"属推测。保留空值降级要求，删除对执行者的预设。
- **H1**：从「必须」降为「推荐 + 若选复用方案须写明理由并补负例」。复用 purpose 并严格校验 `binding_confirmed is True` 同样安全。

**第一轮的 3 处引用错误（已修正）**：`models.py:99`→`:102`、`status-pages-v13.js:34`→`:35`、`status-pages-v13.js:41`→`:40`。

**反向修正一项（本轮升级，非降级）**：L1 原被列为「生产现状待验证」。实测 `infra/nginx/default.conf` 无任何 `access_log` 指令、只有一个 `location /` 全量反代，继承 nginx 默认 combined 格式（`$request` 含 query string），故 raw token 进 nginx 日志是**已确认的确定行为**而非假设，已升级并附整改项。

**本轮新增的证据**：`apps/api/src/schemas/company.py:22` 的状态 pattern 为 `^(ACTIVE|DISABLED|PENDING)$`，`PENDING` 即 M1 所指的中间态；基线测试实测 **10 passed**，说明上述问题均属现有测试未覆盖的设计缺口，而非已知失败。
