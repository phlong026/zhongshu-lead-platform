#!/usr/bin/env python3
"""Generate a concise index for task-level code review records."""
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


def review_files() -> list[Path]:
    """Return review records while excluding generated/legacy index documents."""

    return sorted(
        path
        for path in REVIEWS.glob("*.md")
        if not path.name.upper().startswith("INDEX")
    )


def main() -> int:
    files = review_files()
    metadata = [(path, *review_metadata(path)) for path in files]
    lines = [
        "# 任务级代码评审索引",
        "",
        "> 本索引由 `scripts/generate_review_index.py` 自动生成。`INDEX*.md` 不参与评审记录计数。没有标准评审元数据的历史/上下文文档会保留，但不会误计为“通过”。",
        "",
        f"- 评审/上下文记录总数：**{len(files)}**",
        f"- 明确通过数：**{sum(conclusion == '通过' for _, _, _, _, conclusion in metadata)}**",
        "",
        "| 序号 | 评审任务 | 结论 | 评审时间（UTC） | 评审范围 |",
        "|---:|---|---|---|---|",
    ]
    for index, (path, title, reviewed_at, scope, conclusion) in enumerate(metadata, 1):
        rel = path.relative_to(ROOT).as_posix()
        lines.append(f"| {index} | [{title}](../../{rel}) | {conclusion} | {reviewed_at} | {scope} |")
    lines += [
        "",
        "## 使用规则",
        "",
        "1. 每个开发任务应提交实现、测试与对应评审记录；上下文/预评审文档不得伪装成已通过结论。",
        "2. 评审失败时不得进入发布分支；修复后重新执行对应评审。",
        "3. 生产环境微信、飞书、PostgreSQL、对象存储、恢复演练、UAT 与灰度属于上线 Gate，不以代码级自动检查替代。",
        "",
    ]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
