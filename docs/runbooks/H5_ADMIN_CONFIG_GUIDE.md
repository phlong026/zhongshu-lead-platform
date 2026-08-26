# 合家美宅 H5 与外部服务配置手册

本手册面向开发、运维和验收人员，只描述当前代码已经支持的能力。默认不新增业务功能、新接口或新依赖。

## 1. 当前能力边界

| 项目 | 当前状态 | 说明 |
| --- | --- | --- |
| H5 页面适配 | 已实现 | 加盟商 H5、电销 H5 使用流式宽度，375 是设计基准，不是固定宽度。 |
| 退回证据上传 | 已实现 | 支持沟通截图和电话录音，开发环境可用本地私有目录，生产使用 S3 兼容的私有对象存储。 |
| 审核端在线查看 | 已实现 | 审核人员可在退回详情中查看截图、播放录音；文件下载使用短时效访问凭据并记录审计。 |
| 加盟商微信登录 | 已实现，待外部配置 | 当前是微信公众号网页 OAuth；首次绑定需专属邀请，绑定后可直接授权登录。 |
| 微信通知 | 已实现，待外部配置 | 站内消息、Outbox、微信公众号模板消息适配和失败重试已存在；真实发送依赖公众号资质、模板 ID、用户 OpenID 和调度器。 |
| PC 端微信扫码登录 | 尚未实现 | 当前没有微信开放平台网站应用扫码登录流程；如需支持，属于新功能和新接口范围。 |
| 原生微信小程序授权 | 尚未实现 | 当前产品是微信内 H5，不是原生小程序工程。 |

## 2. H5 宽度与客户端兼容

### 2.1 结论

- 375px 只用作视觉稿和验收基准，页面不应写死为 `width: 375px`。
- 实现应使用 `width: 100%` + `max-width` + 安全区、弹性布局和响应式断点。
- 2x/3x 仅适用于图标、背景图和插图资源，不是页面固定宽度的倍数。
- 按钮、数字卡和底部导航的有效点击高度建议不小于 44px。

### 2.2 建议验收宽度

| CSS 视口宽度 | 用途 |
| --- | --- |
| 320px | 小屏手机和极限宽度 |
| 375px | 标准设计基准 |
| 390px | 当前常见 iPhone 宽度 |
| 414px | 大屏手机 |

每个宽度都要确认：没有水平滚动条、底部导航完整、弹层不超屏、长文案不遮挡操作、数字卡可点击且能进入对应明细。

## 3. 腾讯云 COS 私有对象存储

### 3.1 开发环境

```dotenv
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_DIR=./storage
```

`OBJECT_STORAGE_DIR` 是 API 服务端私有目录，不应由 Nginx 直接公开为静态资源。

### 3.2 生产环境

```dotenv
OBJECT_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://cos.ap-shanghai.myqcloud.com
S3_ACCESS_KEY_ID=replace-with-cos-secret-id
S3_SECRET_ACCESS_KEY=replace-with-cos-secret-key
S3_BUCKET=replace-with-bucket-name-appid
S3_REGION=ap-shanghai
```

说明：

- 当前生产方案固定使用腾讯云 COS 上海地域；代码继续使用现有 S3 兼容适配层，因此环境变量名称保留为 `S3_*`。
- `S3_ACCESS_KEY_ID` 填腾讯云 CAM 子账号的 `SecretId`，`S3_SECRET_ACCESS_KEY` 填对应 `SecretKey`。
- `S3_BUCKET` 必须填写控制台显示的完整 `BucketName-APPID`，不能只填写 BucketName。
- Endpoint 使用地域服务地址 `https://cos.ap-shanghai.myqcloud.com`；客户端会以虚拟主机方式访问完整 Bucket 域名。
- Bucket 必须保持私有读写，不得开启永久公开访问。
- 服务账号至少需要 Bucket 可达检查，以及指定 Bucket/Prefix 下的 `PutObject`、`HeadObject`、`GetObject`、`DeleteObject` 权限。
- 不要把 SecretId、SecretKey 放进前端、Git、截图或聊天记录。
- 切换 Bucket 不会自动迁移旧文件。切换前应保留原 Bucket 和凭据，直到存量证据全部验收。

### 3.3 当前文件规则

- 沟通截图：JPG / PNG / WEBP，单张不超过 5MB。
- 电话录音：MP3 / WAV / M4A / AAC 等已支持格式，单个不超过 20MB。
- 对象路径形如 `evidence/v1.2/年/月/退回申诉ID/随机文件名`。
- 详情接口返回绑定当前用户的 10 分钟访问凭据，下载仍会再检查用户和业务权限。

### 3.4 验证

```bash
python scripts/validate_production_env.py --env-file .env
python scripts/check_object_storage.py --canary
```

`--canary` 会在 `.canary/zhongshu-readiness/` 下执行一次写入、查询、读取和删除。随后还要用业务页完成一次真实验收：

1. 加盟商新建退回申诉。
2. 上传至少 1 张截图和 1 个录音。
3. 退出重登后仍能查看已上传证据。
4. 电销/审核账号能在权限范围内播放，无权账号不能访问。
5. 过期凭据失效，Bucket 仍不可公开读取。

## 4. 微信公众号网页 OAuth

### 4.1 身份边界

当前登录识别的是微信公众号返回的 **OpenID / UnionID**，不是微信号，也无法读取用户自定义的微信号。

当前流程：

1. 新加盟商负责人从平台生成的专属邀请链接进入。
2. 用户确认公司后，后端签发短时效 OAuth state，再进入微信授权。
3. 绑定成功后，可直接访问 `/api/v1/auth/wechat/start?return_url=/h5/#/home` 登录。
4. 不在微信内的 PC 浏览器不会自动获得微信身份。

### 4.2 环境变量

```dotenv
APP_BASE_URL=https://app.example.com
WECHAT_APP_ID=replace-with-official-account-appid
WECHAT_APP_SECRET=replace-with-official-account-secret
WECHAT_OAUTH_SCOPE=snsapi_base
WECHAT_OAUTH_REDIRECT_URI=https://app.example.com/api/v1/auth/wechat/callback
WECHAT_DEV_MOCK=false
```

`WECHAT_OAUTH_SCOPE` 仅支持 `snsapi_base` 或 `snsapi_userinfo`。如果业务不需要昵称等额外信息，优先使用 `snsapi_base`。

### 4.3 微信公众平台需完成

- 确认主体和公众号类型具有所需的网页授权、模板消息权限。
- 将 H5 域名配置为网页授权域名。
- 确保回调地址为 HTTPS，且 host 与 `APP_BASE_URL` 一致。
- AppSecret 只保存在后端秘密管理或部署环境中，不进入前端和版本库。

## 5. 微信通知与 Outbox

### 5.1 能否发送到微信

可以，但真实发送需同时满足：

- `WECHAT_DEV_MOCK=false`；
- 公众号 AppID / AppSecret 有效；
- 用户已绑定可用 OpenID；
- 业务事件对应的模板 ID 已发布；
- `scheduler` 服务持续运行，或由管理员手动触发 Outbox；
- 微信平台对该用户和该模板允许发送。

代码中没有 `OUTBOX_ENABLED` 环境开关。消息会先进入站内通知和 Outbox，调度器再调用微信公众号模板消息接口。

### 5.2 配置模板 ID

模板 ID 保存在系统配置，不是 `.env` 中的固定字段：

- `domain`: `wechat_template`
- `key`: 业务事件名
- `value.template_id`: 微信公众平台中审核通过的模板 ID
- `value.field_map`: 公众号模板字段名到平台业务值的映射；右侧可为 `title`、`scene`、`body`、`remark`，或 `literal:` 开头的固定文案
- `publish_immediately`: `true`

例如，为新客资派发事件 `V12_ASSIGNMENT_DISPATCHED` 发布模板：

```json
{
  "domain": "wechat_template",
  "key": "V12_ASSIGNMENT_DISPATCHED",
  "value": {
    "template_id": "lY0K9b-7pB0bOnfjOJ6zPvPeL5fm0DjPhjxhRUZt3MU",
    "field_map": {
      "thing1": "title",
      "const16": "literal:乡墅新客资"
    }
  },
  "publish_immediately": true
}
```

由超级管理员通过 `POST /api/v1/system-configs` 创建。`field_map` 左侧必须与微信「我的模板 → 详情 → 详细内容」中 `{{...DATA}}` 的原始字段键完全一致；未填写时，为兼容旧配置，适配器仍使用 `first`、`keyword1`、`keyword2`、`remark` 的默认映射。完整的公众号后台操作与首批场景见 `docs/runbooks/WECHAT_TEMPLATE_CONFIGURATION_CHECKLIST.md`。

类目模板若要求一个常量关键词，可用 `literal:` 写入固定文案。例如：

```json
"field_map": {
  "thing1": "title",
  "const16": "literal:乡墅新客资"
}
```

建议至少核对这些 V1.2 事件：

- `V12_ASSIGNMENT_DISPATCHED`
- `V12_ASSIGNMENT_CLAIMED`
- `V12_RETURN_SUBMITTED`
- `V12_RETURN_APPROVED`
- `V12_RETURN_REJECTED`
- `V12_RETURN_NEED_MORE`
- `V12_SUPPLIER_LEAD_SUBMITTED`
- `V12_SUPPLIER_LEAD_APPROVED`
- `V12_SUPPLIER_LEAD_REJECTED`
- `V12_COMPANY_PROFILE_APPROVED`
- `V12_COMPANY_PROFILE_REJECTED`
- `V12_SUPPLIER_REWARD_OBSERVING`
- `V12_SUPPLIER_REWARD_FROZEN`
- `V12_SUPPLIER_REWARD_SETTLED`

### 5.3 调度和失败处理

生产 Docker Compose 中应保持 `scheduler` 服务运行。临时手动验证可执行：

```bash
python scripts/run_jobs.py outbox --limit 100
```

管理员还可在“通知任务”页查看失败任务、重试发送，或调用这些已有接口：

- `GET /api/v1/notifications/gate0`：查看公众号配置、测试模式和 HTTPS 状态。
- `GET /api/v1/notifications/outbox/failed`：查看失败、终止或需人工处理的任务。
- `POST /api/v1/notifications/outbox/{id}/retry`：将任务重置为待发送。
- `POST /api/v1/notifications/jobs/process-outbox?limit=100`：由超级管理员立即处理一批。

失败状态：

- `FAILED`：暂时失败，调度器按退避时间重试。
- `DEAD`：连续失败达到上限，需运维或管理员介入。
- `MANUAL_ACTION_REQUIRED`：未配置模板或没有可用收件人，自动重试无法解决。

特别边界：“加盟邀请已创建”发生在被邀请人绑定微信之前，真实环境没有收件人 OpenID，因此当前仍需运营人员复制邀请链接手动发送。

## 6. 飞书配置的正确定位

飞书是可选的历史客资导入/回写数据源，不是当前 Outbox 的消息通知通道。如果不使用飞书同步，保持：

```dotenv
FEISHU_ENABLED=false
FEISHU_DEV_MOCK=false
```

如果需保留历史同步，再配置 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_APP_TOKEN`、`FEISHU_TABLE_ID`、`FEISHU_FIELD_MAPPING_JSON` 等字段。飞书同步是独立作业，不能替代微信消息模板配置。

## 7. 生产配置与验收顺序

### 7.1 配置顺序

1. 配置 HTTPS 域名、`APP_BASE_URL`、`CORS_ORIGINS`、`TRUSTED_HOSTS`和反向代理信任。
2. 配置 PostgreSQL，确保 `AUTO_CREATE_SCHEMA=false`、`LEGACY_WRITE_ENABLED=false`。
3. 配置真实对象存储，执行 canary。
4. 配置真实微信公众号 OAuth，在 iOS/Android 微信中完成首次绑定和重复登录。
5. 发布微信模板 ID，启动 scheduler，验证 Outbox 成功、失败和人工处理路径。
6. 使用 320 / 375 / 390 / 414 宽度做页面验收，再做真机验收。

### 7.2 自动预检

```bash
python scripts/validate_production_env.py --env-file .env
python scripts/check_object_storage.py --canary
python scripts/verify_production.py --env-file .env --require-certificates
```

随后检查：

- `GET /health/live`：进程存活。
- `GET /health/ready`：数据库和对象存储就绪。
- `/api/v1/notifications/gate0`：微信通道配置和 HTTPS 边界正确。

## 8. 回滚和安全要求

- 变更前备份 `.env` 的密文版本或密钥管理版本，不要把真实凭据复制到文档或提交记录。
- 对象存储回滚应恢复上一组已验证的 S3 配置；不要在生产直接回退到本地目录。
- 微信模板配置是版本化系统配置；发布新版本前记录旧模板 ID，方便恢复。
- 如果外部通道暂时不可用，保留站内消息和 Outbox 失败记录，不要直接删除任务来“清空报错”。
- 未完成真实微信公众号、真实对象存储和移动真机验收前，只能标记为本地已验证，不能标记为生产可用。
