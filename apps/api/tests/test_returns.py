import pytest
from datetime import datetime, timezone

from apps.api.src.core.auth import Principal
from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Assignment, Lead, ReturnEvidence
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.points_service import change_points
from apps.api.src.services.return_service import add_evidence, create_or_update_return, review_return, submit_return


def p(uid, company, role, perms):
    return Principal(user_id=uid,display_name=role,company_id=company,role_codes=frozenset({role}),permission_codes=frozenset(perms),session_version=1)


def setup(db):
    company=create_company(db,CompanyCreateBody(code="RET1",name="退回公司"))
    lead=Lead(customer_name="客户",phone_encrypted=encrypt_text("13800138000"),phone_hash=hash_phone("13800138000"),status="CLAIMED")
    db.add(lead);db.flush()
    assignment=Assignment(lead_id=lead.id,company_id=company.id,status="CLAIMED",points_price=100,price_version=1,lead_snapshot={},assigned_by="op",claimed_at=datetime.now(timezone.utc))
    db.add(assignment);db.flush()
    change_points(db,company_id=company.id,delta=500,ledger_type="ADJUST",business_type="SEED",business_id="seed",idempotency_key="ret-seed-01",created_by=None)
    change_points(db,company_id=company.id,delta=-100,ledger_type="CLAIM",business_type="ASSIGNMENT",business_id=assignment.id,idempotency_key="ret-claim-01",created_by="owner")
    db.commit();return company,lead,assignment


@pytest.mark.parametrize(
    ("evidence_type", "object_key", "mime_type", "duration_seconds"),
    [
        ("CHAT_SCREENSHOT", "evidence.png", "image/png", None),
        ("CALL_RECORDING", "evidence.mp3", "audio/mpeg", 10),
    ],
)
def test_return_accepts_either_evidence_and_refunds_once(
    db,
    evidence_type,
    object_key,
    mime_type,
    duration_seconds,
):
    company,lead,assignment=setup(db)
    owner=p("owner",company.id,"FRANCHISE_OWNER",{"return.own.manage"})
    reviewer=p("reviewer",None,"RETURN_REVIEWER",{"return.review"})
    item=create_or_update_return(db,assignment=assignment,principal=owner,reason_code="EMPTY_NUMBER",description="电话为空号")
    db.commit()
    with pytest.raises(AppError) as exc: submit_return(db,item,owner)
    assert exc.value.code=="RETURN_EVIDENCE_REQUIRED"
    add_evidence(
        db,
        request=item,
        evidence_type=evidence_type,
        object_key=object_key,
        original_name=object_key,
        mime_type=mime_type,
        file_size=1,
        sha256="a"*64,
        duration_seconds=duration_seconds,
        uploaded_by="owner",
    )
    submit_return(db,item,owner)
    ledger=review_return(db,request=item,principal=reviewer,decision="APPROVE",note="证据有效")
    db.commit()
    assert item.status=="APPROVED"
    assert ledger.delta==100
    assert assignment.status=="RETURNED"
    assert lead.current_assignment_id is None
    with pytest.raises(AppError): review_return(db,request=item,principal=reviewer,decision="APPROVE",note="重复")
