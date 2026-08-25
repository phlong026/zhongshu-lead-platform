from pathlib import Path


def test_operations_exposes_a_dedicated_full_process_trace_view() -> None:
    source = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    styles = Path("apps/admin/public/v12-operations.css").read_text(encoding="utf-8")
    browser_smoke = Path("scripts/browser_smoke_v12.py").read_text(encoding="utf-8")

    assert "trace:['客资详情'" in source
    assert "async function fullTrace()" in source
    assert "处理进度" in source
    assert "处理记录" in source
    assert "派发信息" in source
    assert "退回审核" in source
    assert "申诉证据" in source
    assert "积分与奖励" in source
    assert "go('trace',x.id)" in source
    assert "等待补齐客户信息后提交初审" in source
    assert "ops-trace-layout" in styles
    assert "ops-trace-timeline" in styles
    assert "v12-full-process-detail.png" in browser_smoke
    assert ".ops-trace-layout" in browser_smoke
    assert "/api/v1/v1.2/platform/leads" in browser_smoke
    assert "modal('完整业务记录'" not in source
