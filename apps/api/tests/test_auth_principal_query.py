from __future__ import annotations

from sqlalchemy import event, select

from apps.api.src.core.auth import load_current_principal
from apps.api.src.core.models import Company, Role, User, UserRole


def _principal_fixture(db):
    company = Company(code="PRINCIPAL-QUERY", name="Principal Query Company", status="ACTIVE")
    user = User(
        username="principal-query-user",
        password_hash="not-used",
        display_name="Principal Query User",
        status="ACTIVE",
        session_version=3,
        company=company,
    )
    db.add_all([company, user])
    db.flush()
    for code in ("FRANCHISE_OWNER", "OWNER"):
        role = db.scalar(select(Role).where(Role.code == code))
        assert role is not None
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return company, user


def test_principal_and_permissions_load_in_one_query(db) -> None:
    _, user = _principal_fixture(db)
    statements: list[str] = []

    def record_statement(*args) -> None:
        statements.append(args[2])

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        principal = load_current_principal(db, user.id, user.session_version)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert principal is not None
    assert principal.role_codes == frozenset({"FRANCHISE_OWNER", "OWNER"})
    assert "assignment.own.read" in principal.permission_codes
    assert "dashboard.finance.read" in principal.permission_codes
    assert len(statements) == 1


def test_principal_query_preserves_session_and_company_invalidation(db) -> None:
    company, user = _principal_fixture(db)

    assert load_current_principal(db, user.id, user.session_version + 1) is None

    company.status = "DISABLED"
    db.commit()
    assert load_current_principal(db, user.id, user.session_version) is None

    company.status = "ACTIVE"
    user.status = "DISABLED"
    db.commit()
    assert load_current_principal(db, user.id, user.session_version) is None
