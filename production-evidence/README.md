# production-evidence 归档目录

生产上线证据统一归档于此（宿主机侧），与 `docs/runbooks/V1.2_PRODUCTION_EXECUTION_PLAN.md` 第 12 节一致。

## 结构

```text
production-evidence/
  <YYYY-MM-DD>-<phase>-<version>/   # 例如 2026-08-12-p1-infrastructure
    <evidence>.json                 # 脱敏 JSON 证据
    README.md                       # 该批次说明（可选）
```

## 规则

- 只归档可核验、可复现的证据；失败证据同样保留，禁止只留“成功截图”；
- 任何 Secret（密码、SecretKey、Token、私钥、AppSecret）不得写入本目录；
- 手机号等个人数据如出现必须脱敏；
- JSON 证据必须通过 `python -m json.tool` 校验；
- 归档文件路径与摘要写入对应 Issue/PR 作为追溯链接。

## P1 基础设施证据模板

`p1-infrastructure-evidence.template.json` 为 Issue #42 验收证据模板，
由 `scripts/verify_infrastructure.py --output production-evidence/...` 实际生成。