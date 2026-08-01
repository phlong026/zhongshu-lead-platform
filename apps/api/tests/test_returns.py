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


def test_return_requires_both_evidence_and_refunds_once(db):
    company,lead,assignment=setup(db)
    owner=p("owner",company.id,"FRANCHISE_OWNER",{"return.own.manage"})
    reviewer=p("reviewer",None,"RETURN_REVIEWER",{"return.review"})
    item=create_or_update_return(db,assignment=assignment,principal=owner,reason_code="EMPTY_NUMBER",description="电话为空号")
    db.commit()
    with pytest.raises(AppError) as exc: submit_return(db,item,owner)
    assert exc.value.code=="RETURN_SCREENSHOT_REQUIRED"
    add_evidence(db,request=item,evidence_type="CHAT_SCREENSHOT",object_key="x.png",original_name="x.png",mime_type="image/png",file_size=1,sha256="a"*64,duration_seconds=None,uploaded_by="owner")
    add_evidence(db,request=item,evidence_type="CALL_RECORDING",object_key="x.mp3",original_name="x.mp3",mime_type="audio/mpeg",file_size=1,sha256="b"*64,duration_seconds=10,uploaded_by="owner")
    submit_return(db,item,owner)
    ledger=review_return(db,request=item,principal=reviewer,decision="APPROVE",note="证据有效")
    db.commit()
    assert item.status=="APPROVED"
    assert ledger.delta==100
    assert assignment.status=="RETURNED"
    assert lead.current_assignment_id is None
    with pytest.raises(AppError): review_return(db,request=item,principal=reviewer,decision="APPROVE",note="重复")
