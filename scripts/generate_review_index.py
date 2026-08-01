#!/usr/bin/env python3
"""Generate a concise index for all task-level code review records."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "docs" / "reviews"
OUTPUT = REVIEWS / "INDEX.md"


def review_metadata(path: Path) -> tuple[str, str, str, str]:
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^# 代码评审：(.+)$", text, re.MULTILINE)
    time_match = re.search(r"^- 评审时间：(.+)$", text, re.MULTILINE)
    scope_match = re.search(r"^- 评审范围：(.+)$", text, re.MULTILINE)
    conclusion_match = re.search(r"^- 总体结论：(.+)$", text, re.MULTILINE)
    return (
        title_match.group(1) if title_match else path.stem,
        time_match.group(1) if time_match else "-",
        scope_match.group(1) if scope_match else "-",
        conclusion_match.group(1) if conclusion_match else "未记录",
    )


def main() -> int:
    files = sorted(path for path in REVIEWS.glob("*.md") if path.name != OUTPUT.name)
    lines = [
        "# 任务级代码评审索引",
        "",
        "> 本索引由 `scripts/generate_review_index.py` 自动生成。每一项任务在提交前均执行 Python 编译、后端测试、前端 JavaScript 语法检查与敏感信息扫描。",
        "",
        f"- 评审记录总数：**{len(files)}**",
        f"- 通过数：**{sum(review_metadata(path)[3] == '通过' for path in files)}**",
        "",
        "| 序号 | 评审任务 | 结论 | 评审时间（UTC） | 评审范围 |",
        "|---:|---|---|---|---|",
    ]
    for index, path in enumerate(files, 1):
        title, reviewed_at, scope, conclusion = review_metadata(path)
        rel = path.relative_to(ROOT).as_posix()
        lines.append(f"| {index} | [{title}](../../{rel}) | {conclusion} | {reviewed_at} | {scope} |")
    lines += [
        "",
        "## 使用规则",
        "",
        "1. 每个小任务必须同时提交实现、测试与对应评审记录。",
        "2. 评审失败时不得进入主分支；修复后重新执行同一任务评审。",
        "3. 生产环境微信、飞书、PostgreSQL 和对象存储联调属于上线 Gate，不以本地自动检查替代。",
        "",
    ]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
