from apps.api.src.core.auth import Principal
from apps.api.src.core.models import Assignment, Lead
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.services.followup_service import add_followup


def test_followup_is_append_only_and_updates_current_state(db) -> None:
    lead=Lead(customer_name="客户",phone_encrypted=encrypt_text("13800138000"),phone_hash=hash_phone("13800138000"),status="CLAIMED")
    db.add(lead); db.flush()
    assignment=Assignment(lead_id=lead.id,company_id="company-1",status="CLAIMED",points_price=100,price_version=1,lead_snapshot={},assigned_by="op")
    db.add(assignment); db.flush()
    principal=Principal(user_id="owner",display_name="老板",company_id="company-1",role_codes=frozenset({"FRANCHISE_OWNER"}),permission_codes=frozenset({"followup.own.manage"}),session_version=1)
    first=add_followup(db,assignment=assignment,principal=principal,status="CONTACTED",note="已沟通",next_followup_at=None)
    second=add_followup(db,assignment=assignment,principal=principal,status="INTERESTED",note="有意向",next_followup_at=None)
    db.commit()
    assert first.id != second.id
    assert assignment.status == "FOLLOWING"
    assert lead.current_follow_status == "INTERESTED"


def test_overdue_job_is_idempotent(db):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func, select

    from apps.api.src.core.models import Assignment, Lead, Notification, NotificationOutbox
    from apps.api.src.core.security import encrypt_text, hash_phone
    from apps.api.src.schemas.company import CompanyCreateBody
    from apps.api.src.services.company_service import create_company
    from apps.api.src.services.followup_service import run_followup_overdue

    company = create_company(db, CompanyCreateBody(code="OD1", name="超时提醒公司"))
    lead = Lead(
        customer_name="超时客户",
        phone_encrypted=encrypt_text("13800138006"),
        phone_hash=hash_phone("13800138006"),
        status="CLAIMED",
    )
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=company.id,
        status="CLAIMED",
        points_price=100,
        price_version=1,
        lead_snapshot={},
        assigned_by="op",
        claimed_at=datetime.now(timezone.utc) - timedelta(hours=72),
        first_followup_due_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(assignment)
    db.commit()

    first = run_followup_overdue(db)
    db.commit()
    second = run_followup_overdue(db)
    db.commit()

    assert first == {"overdue": 1, "notified": 1}
    assert second == {"overdue": 1, "notified": 0}
    assert db.scalar(select(func.count(Notification.id)).where(Notification.scene == "FOLLOWUP_OVERDUE")) == 1
    assert db.scalar(select(func.count(NotificationOutbox.id)).where(NotificationOutbox.event_type == "FOLLOWUP_OVERDUE")) == 1
