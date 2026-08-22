from __future__ import annotations


def test_cli_exit_code_follows_severity(db, capsys) -> None:
    """N2：check_binding_integrity CLI 是发布/启动门禁——error 级违规 exit 1。"""

    from scripts.check_binding_integrity import evaluate

    assert evaluate(db) == 0, "干净库必须 exit 0"

    from apps.api.src.core.models import Company

    db.add(
        Company(
            code="N2-CLI",
            name="悬空主账号公司",
            status="ACTIVE",
            primary_user_id="ghost-user-id",
        )
    )
    db.commit()
    assert evaluate(db) == 1
    output = capsys.readouterr().out
    assert "DANGLING_PRIMARY" in output, "报告必须打印违规码供门禁日志留痕"
