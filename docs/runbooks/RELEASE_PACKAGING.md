# 代码发布与打包手册

## 1. 发布前检查

```bash
git status --short
pytest -q
python scripts/task_review.py --task <任务号> --title <任务名称>
python scripts/generate_review_index.py
```

发布前必须保证工作区干净，所有实现、测试与评审记录已经提交。

## 2. 创建版本标签

```bash
git tag -a v1.0.0-p0 -m "众墅之家客资平台 P0"
```

## 3. 生成交付包

```bash
python scripts/package_release.py \
  --version V1.0.0-P0 \
  --output-dir /mnt/data
```

输出包括：

- 完整源码 ZIP：仅含 Git 已跟踪文件，不含运行数据、私有证据或 `.env`；
- Git Bundle：包含完整提交历史和标签；
- 完整交付包 ZIP：组合源码、Git 历史、质量报告、发布说明和校验文件；
- SHA256 校验文件。

## 4. 恢复 Git 仓库

```bash
git clone 众墅之家客资平台_V1.0.0-P0_完整Git提交历史.bundle zhongshu-lead-platform
cd zhongshu-lead-platform
git log --oneline --decorate
```

## 5. 校验文件

```bash
sha256sum -c 众墅之家客资平台_V1.0.0-P0_SHA256SUMS.txt
```

## 6. 安全边界

打包脚本只读取 `git ls-files`，并额外阻止以下内容进入源码包：

- `.env`；
- SQLite/数据库文件；
- `storage/` 私有上传目录；
- Python/测试缓存；
- 覆盖率运行文件。

真实生产密钥必须通过环境变量或密钥管理服务配置，不得提交到 Git。
