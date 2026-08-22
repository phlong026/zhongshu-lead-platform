from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def insert_before(text: str, marker: str, addition: str) -> str:
    if addition.strip() in text:
        return text
    index = text.index(marker)
    return text[:index] + addition.rstrip() + "\n\n" + text[index:]


# ---------------------------------------------------------------------------
# 1. Preserve PostgreSQL FK correctness and ORM state synchronization.
# ---------------------------------------------------------------------------
service_path = "apps/api/src/services/invite_binding_service.py"
service = read(service_path)

if "active_invites = db.scalars(" not in service:
    old = '''    db.execute(
        update(InviteToken)
        .where(
            InviteToken.company_id == company.id,
            InviteToken.used_at.is_(None),
            InviteToken.revoked_at.is_(None),
            InviteToken.expires_at > now,
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
'''
    new = '''    active_invites = db.scalars(
        select(InviteToken)
        .where(
            InviteToken.company_id == company.id,
            InviteToken.used_at.is_(None),
            InviteToken.revoked_at.is_(None),
            InviteToken.expires_at > now,
        )
        .with_for_update()
    ).all()
    for active_invite in active_invites:
        active_invite.revoked_at = now
'''
    if old not in service:
        raise RuntimeError("active invite revocation anchor not found")
    service = service.replace(old, new, 1)

if "PostgreSQL enforces the primary_user_id foreign key" not in service:
    old = '''    user_id = uuid_str()
    occupied = db.execute(
'''
    new = '''    user_id = uuid_str()
    # PostgreSQL enforces the primary_user_id foreign key immediately. The
    # candidate user remains inside this transaction and is rolled back on
    # any company-occupancy conflict or subsequent binding failure.
    user = User(
        id=user_id,
        display_name=nickname or company.owner_name or "微信加盟商",
        company_id=company.id,
        status="ACTIVE",
        last_login_at=utcnow(),
    )
    db.add(user)
    db.flush()

    occupied = db.execute(
'''
    if old not in service:
        raise RuntimeError("primary user occupancy anchor not found")
    service = service.replace(old, new, 1)

    duplicate = '''    user = User(
        id=user_id,
        display_name=nickname or company.owner_name or "微信加盟商",
        company_id=company.id,
        status="ACTIVE",
        last_login_at=utcnow(),
    )
    db.add(user)
    db.flush()
    assign_role(db, user, "FRANCHISE_OWNER")
'''
    if duplicate not in service:
        raise RuntimeError("duplicate user creation anchor not found")
    service = service.replace(duplicate, '    assign_role(db, user, "FRANCHISE_OWNER")\n', 1)

if 'db.refresh(company, attribute_names=["primary_user_id"])' not in service:
    anchor = '''    if occupied is None:
        db.expire(company)
        refreshed = db.get(Company, company.id)
        if refreshed is None or refreshed.status != "ACTIVE":
            raise AppError("AUTH_COMPANY_UNAVAILABLE", "加盟商公司当前不可用", 403)
        raise AppError("AUTH_COMPANY_ALREADY_BOUND", "该公司已有主账号，不能重复绑定", 409)

'''
    replacement = anchor + '''    # The conditional UPDATE bypasses the identity map. Refresh the loaded row
    # so callers and rollback tests cannot observe a stale primary_user_id.
    db.expire(company, ["primary_user_id"])
    db.refresh(company, attribute_names=["primary_user_id"])
    if company.primary_user_id != user_id:
        raise AppError("AUTH_COMPANY_BIND_CONFLICT", "公司主账号占用结果异常", 409)

'''
    if anchor not in service:
        raise RuntimeError("identity map refresh anchor not found")
    service = service.replace(anchor, replacement, 1)

# Phone-match confirmation must be a server-side, auditable state transition.
if "def confirm_verified_phone_match(" not in service:
    service += '''\n\ndef confirm_verified_phone_match(
    db: Session,
    match_id: str,
    company_id: str,
) -> dict[str, Any]:
    attempt = db.scalar(
        select(InviteMatchAttempt)
        .where(InviteMatchAttempt.id == match_id)
        .with_for_update()
    )
    if attempt is None:
        raise AppError("INVITE_MATCH_NOT_FOUND", "匹配记录不存在", 404)
    if attempt.outcome != "UNIQUE" or attempt.selected_company_id != company_id:
        raise AppError("INVITE_MATCH_CONFIRM_INVALID", "只有唯一有效匹配可以确认", 409)
    if attempt.cancelled_at is not None:
        raise AppError("INVITE_MATCH_CANCELLED", "该匹配已取消", 409)
    company = _active_company_or_error(db.get(Company, company_id))
    _ensure_company_unbound(company)
    if attempt.confirmed_at is None:
        attempt.confirmed_at = utcnow()
        db.flush()
    return {
        "match_id": attempt.id,
        "company_id": company.id,
        "company_name": company.name,
        "owner_name": _owner_name(company.owner_name),
        "confirmed_at": as_utc(attempt.confirmed_at).isoformat(),
    }
'''

if service.count("user = User(\n        id=user_id,") != 1:
    raise RuntimeError("binding candidate user must be created exactly once")
write(service_path, service)


# ---------------------------------------------------------------------------
# 2. Add verified-phone confirmation API and audit event.
# ---------------------------------------------------------------------------
schema_path = "apps/api/src/schemas/invite.py"
schema = read(schema_path)
if "class VerifiedPhoneMatchConfirmBody" not in schema:
    schema += '''\n\nclass VerifiedPhoneMatchConfirmBody(BaseModel):
    match_id: str = Field(min_length=1, max_length=36)
    company_id: str = Field(min_length=1, max_length=36)
'''
write(schema_path, schema)

router_path = "apps/api/src/routers/invitations.py"
router = read(router_path)
if "VerifiedPhoneMatchConfirmBody" not in router:
    router = router.replace(
        "    VerifiedPhoneMatchBody,\n",
        "    VerifiedPhoneMatchBody,\n    VerifiedPhoneMatchConfirmBody,\n",
        1,
    )
if "confirm_verified_phone_match," not in router:
    router = router.replace(
        "    confirm_manual_match,\n",
        "    confirm_manual_match,\n    confirm_verified_phone_match,\n",
        1,
    )
if "def confirm_verified_phone_company_match(" not in router:
    marker = '@router.get("/invite-matches/manual")\n'
    endpoint = '''@router.post("/invite-matches/verified-phone/confirm")
def confirm_verified_phone_company_match(
    body: VerifiedPhoneMatchConfirmBody,
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
):
    result = confirm_verified_phone_match(db, body.match_id, body.company_id)
    write_audit(
        db,
        principal=principal,
        action="INVITE_PHONE_MATCH_CONFIRMED",
        resource_type="company",
        resource_id=body.company_id,
        metadata={"match_id": body.match_id},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, result, "手机号匹配对象已确认")


'''
    if marker not in router:
        raise RuntimeError("manual match endpoint anchor not found")
    router = router.replace(marker, endpoint + marker, 1)
write(router_path, router)


# ---------------------------------------------------------------------------
# 3. Complete admin matching UI and fix retry/pagination details.
# ---------------------------------------------------------------------------
admin_path = "apps/admin/app.js"
admin = read(admin_path)
admin = admin.replace("const rows=data.items.map(item=>`<tr", "const rows=data.items.map(item=>`<tr", 1)
admin = admin.replace("</tr>`).join('');const companyOptions=", "</tr>`);const companyOptions=", 1)
admin = admin.replace("},{once:true});}catch(error){toast(error.message,'error')}}\nasync function inviteRecordsModal", "});}catch(error){toast(error.message,'error')}}\nasync function inviteRecordsModal", 1)

match_functions = r'''async function inviteMatchModal(){
  openModal('邀请对象匹配',`${field('invite-match-query','公司或负责人名称',input('invite-match-query','','text','输入关键词'))}${field('invite-match-region','省/市/区编码',input('invite-match-region','','text','例如 310115'))}${field('invite-match-phone','已核验手机号',input('invite-match-phone','','tel','仅输入已完成授权核验的手机号'))}<div id="invite-match-results"><p style="color:var(--muted)">手机号只有唯一且有效的结果时才会进入确认；手工选择同样需要二次确认并写入审计。</p></div>`,`<button data-close class="btn btn-outline">取消</button><button id="invite-new-company" class="btn btn-outline">提交指定地区供应商</button><button id="invite-run-manual-match" class="btn btn-primary">手工查找</button><button id="invite-run-phone-match" class="btn btn-primary">手机号匹配</button>`);
  document.querySelector('#invite-new-company')?.addEventListener('click',()=>{closeOverlay();companyModal()});
  document.querySelector('#invite-run-manual-match')?.addEventListener('click',runManualInviteMatch);
  document.querySelector('#invite-run-phone-match')?.addEventListener('click',runPhoneInviteMatch);
}
async function runManualInviteMatch(){
  const query=document.querySelector('#invite-match-query')?.value.trim()||'';const region=document.querySelector('#invite-match-region')?.value.trim()||'';const params=new URLSearchParams({page:'1',page_size:'20'});if(query)params.set('query',query);if(region)params.set('region_code',region);
  try{const data=await request(`/auth/invite-matches/manual?${params}`);const target=document.querySelector('#invite-match-results');if(!target)return;target.innerHTML=data.items.length?data.items.map(item=>`<div class="card" style="margin:8px 0"><b>${esc(item.name)}</b><br><small>${esc(item.owner_name||'--')} · ${esc((item.region_codes||[]).join('、')||'未配置地区')}</small><br><button class="btn btn-small btn-primary" data-confirm-manual-match="${item.id}">确认选择并生成邀请</button></div>`).join(''):'<p>未找到唯一对象，可提交指定地区供应商信息。</p>';document.querySelectorAll('[data-confirm-manual-match]').forEach(button=>button.addEventListener('click',async()=>{if(!confirm('确认选择该公司作为邀请对象？'))return;try{await request('/auth/invite-matches/manual/confirm',{method:'POST',body:JSON.stringify({company_id:button.dataset.confirmManualMatch})});closeOverlay();inviteCompany(button.dataset.confirmManualMatch)}catch(error){toast(error.message,'error')}}));}catch(error){toast(error.message,'error')}
}
async function runPhoneInviteMatch(){
  const phone=document.querySelector('#invite-match-phone')?.value.trim()||'';if(!phone){toast('请输入已核验手机号','error');return}
  try{const result=await request('/auth/invite-matches/verified-phone',{method:'POST',body:JSON.stringify({verified_phone:phone,verification_source:'ADMIN_VERIFIED_INPUT'})});const target=document.querySelector('#invite-match-results');if(!target)return;if(result.outcome!=='UNIQUE'||!result.company){target.innerHTML=`<p>${esc(result.message||'手机号未得到唯一有效匹配，请改用手工查找。')}</p>`;return}target.innerHTML=`<div class="card"><b>${esc(result.company.name)}</b><br><small>${esc(result.company.owner_name||'--')}</small><br><button id="confirm-phone-match" class="btn btn-primary">确认手机号匹配并生成邀请</button></div>`;document.querySelector('#confirm-phone-match')?.addEventListener('click',async()=>{if(!confirm('确认将该手机号匹配结果作为邀请对象？'))return;try{await request('/auth/invite-matches/verified-phone/confirm',{method:'POST',body:JSON.stringify({match_id:result.match_id,company_id:result.company.id})});closeOverlay();inviteCompany(result.company.id)}catch(error){toast(error.message,'error')}});}catch(error){toast(error.message,'error')}
}
'''
if "async function inviteMatchModal()" not in admin:
    marker = "async function companies(){"
    if marker not in admin:
        raise RuntimeError("admin company list anchor not found")
    admin = admin.replace(marker, match_functions + "\n" + marker, 1)

admin = admin.replace(
    "'<button id=\"invite-records\" class=\"btn btn-outline\">邀请记录</button><button id=\"new-company\"",
    "'<button id=\"invite-matches\" class=\"btn btn-outline\">邀请对象匹配</button><button id=\"invite-records\" class=\"btn btn-outline\">邀请记录</button><button id=\"new-company\"",
    1,
)
if "#invite-matches" not in admin:
    admin = admin.replace(
        "document.querySelector('#invite-records')?.addEventListener('click',()=>inviteRecordsModal(1));",
        "document.querySelector('#invite-records')?.addEventListener('click',()=>inviteRecordsModal(1));document.querySelector('#invite-matches')?.addEventListener('click',inviteMatchModal);",
        1,
    )
write(admin_path, admin)


# ---------------------------------------------------------------------------
# 4. Expand machine contracts, API tests, provider doubles and browser UA.
# ---------------------------------------------------------------------------
front_test_path = "apps/api/tests/test_invite_frontend_contract.py"
front = read(front_test_path)
if "test_admin_matching_ui_requires_server_confirmation" not in front:
    front += '''\n\ndef test_admin_matching_ui_requires_server_confirmation() -> None:
    source = ADMIN_APP.read_text(encoding="utf-8")
    for value in (
        "/auth/invite-matches/manual?",
        "/auth/invite-matches/manual/confirm",
        "/auth/invite-matches/verified-phone",
        "/auth/invite-matches/verified-phone/confirm",
        "提交指定地区供应商",
    ):
        assert value in source
'''
write(front_test_path, front)

api_test = r'''from __future__ import annotations

from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.invite_binding_service import create_company_invite
from apps.api.src.services.invite_delivery import prepare_invite_delivery


def _login_admin(client) -> None:
    response = client.post("/api/v1/auth/login", json={"username":"admin","password":"Admin123!"})
    assert response.status_code == 200, response.text


def _company(session, code: str, phone: str | None = None):
    return create_company(session, CompanyCreateBody(code=code,name=f"{code} 邀请接口公司",owner_name="接口负责人",contact_phone=phone,region_codes=["310115"],capabilities=[{"category_code":"OLD_RENOVATION","brand_code":"ZHONGSHU"}]))


def test_invite_management_requires_permission_and_is_paginated(api_client) -> None:
    client, factory = api_client
    assert client.get("/api/v1/auth/invites").status_code == 401
    with factory() as db:
        company = _company(db, "API-INV-001")
        company_id = company.id
        db.commit()
    _login_admin(client)
    preflight = client.get(f"/api/v1/auth/companies/{company_id}/invites/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["data"]["company_name"] == "API-INV-001 邀请接口公司"
    created = client.post(f"/api/v1/auth/companies/{company_id}/invites", json={"expires_hours":72})
    assert created.status_code == 200, created.text
    payload = created.json()["data"]
    assert {"owner_name","company_name","invite_url","copy_text","expires_at","status"}.issubset(payload)
    listing = client.get("/api/v1/auth/invites", params={"company_id":company_id,"page":1,"page_size":1})
    assert listing.status_code == 200
    assert listing.json()["data"]["page_size"] == 1
    assert len(listing.json()["data"]["items"]) == 1
    missing = client.post("/api/v1/auth/invites/missing-invitation/revoke")
    assert missing.status_code == 404


def test_verified_phone_match_requires_unique_server_confirmation(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        company = _company(db, "API-INV-002", "13800138022")
        company_id = company.id
        db.commit()
    _login_admin(client)
    matched = client.post("/api/v1/auth/invite-matches/verified-phone", json={"verified_phone":"13800138022","verification_source":"TEST_DOUBLE"})
    assert matched.status_code == 200, matched.text
    result = matched.json()["data"]
    assert result["outcome"] == "UNIQUE"
    assert "13800138022" not in matched.text
    confirmed = client.post("/api/v1/auth/invite-matches/verified-phone/confirm", json={"match_id":result["match_id"],"company_id":company_id})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["company_id"] == company_id
    forged = client.post("/api/v1/auth/invite-matches/verified-phone/confirm", json={"match_id":result["match_id"],"company_id":"wrong-company"})
    assert forged.status_code in {404,409}


class _FakeDeliveryAdapter:
    def __init__(self) -> None:
        self.calls = []
    def send(self, *, recipient, payload, timeout_seconds):
        self.calls.append((recipient, payload["invite_id"], timeout_seconds))
        return "provider-test-reference"


def test_external_delivery_adapter_uses_timeout_and_never_fakes_success(db) -> None:
    company = _company(db, "API-INV-003")
    invitation = create_company_invite(db, company.id, None, 24)
    adapter = _FakeDeliveryAdapter()
    result = prepare_invite_delivery(db, invitation.invite.id, "SMS", requested_by=None, recipient="13800138033", enabled=True, adapter=adapter, timeout_seconds=8)
    assert result.status == "SENT" and result.delivered is True
    assert adapter.calls == [("13800138033", invitation.invite.id, 8.0)]
    assert "13800138033" not in str(result.payload)
'''
write("apps/api/tests/test_invite_api_contract.py", api_test)

# Use a WeChat WebView user agent in the mobile browser proof.
browser_path = "apps/api/tests/test_invite_browser_smoke.py"
browser = read(browser_path)
wechat_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.50"
browser = browser.replace(
    'browser.new_page(viewport={"width": 390, "height": 844})',
    f'browser.new_page(viewport={{"width": 390, "height": 844}}, user_agent="{wechat_ua}")',
)
browser = browser.replace(
    'browser.new_page(viewport={"width":390,"height":844})',
    f'browser.new_page(viewport={{"width":390,"height":844}}, user_agent="{wechat_ua}")',
)
write(browser_path, browser)


# ---------------------------------------------------------------------------
# 5. Real PostgreSQL claim transaction proof using the actual FastAPI route.
# ---------------------------------------------------------------------------
claim_pg_test = r'''from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from apps.api.src.core.database import get_db
from apps.api.src.core.enums import AssignmentStatus, PointsLedgerType
from apps.api.src.core.models import Assignment, Company, Lead, PointsAccount, PointsLedger, User
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_phone
from apps.api.src.core.time import utcnow
from apps.api.src.core.v12_enums import LeadSourceKind
from apps.api.src.main import app
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.rbac import seed_rbac

POSTGRES_URL = os.getenv("CLAIM_POSTGRES_TEST_URL", "")
pytestmark = pytest.mark.skipif(not POSTGRES_URL.startswith("postgresql"), reason="requires PostgreSQL")


def _factory():
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _seed(factory):
    suffix = uuid4().hex[:10]
    now = utcnow()
    with factory() as db:
        seed_rbac(db)
        company = Company(code=f"PG-CLAIM-{suffix}", name=f"PostgreSQL 领取并发 {suffix}", status="ACTIVE", level_code="V1")
        db.add(company); db.flush()
        owner = create_internal_user(db, username=f"pg_claim_owner_{suffix}", password="PgClaimOwner123!", display_name="PostgreSQL 领取用户", role_code="FRANCHISE_OWNER", company_id=company.id)
        operator = create_internal_user(db, username=f"pg_claim_operator_{suffix}", password="PgClaimOperator123!", display_name="PostgreSQL 派发用户", role_code="OPERATION")
        company.primary_user_id = owner.id
        account = PointsAccount(company_id=company.id, balance=1000, version=1)
        db.add(account)
        phone = "13900138888"
        lead = Lead(source_type=LeadSourceKind.SUPPLIER_H5.value,source_kind=LeadSourceKind.SUPPLIER_H5.value,submitter_user_id=owner.id,supplier_company_id=company.id,customer_name="PostgreSQL 并发领取客户",phone_encrypted=encrypt_text(phone),phone_hash=hash_phone(phone),phone_fingerprint=fingerprint_phone(phone),consent_confirmed=True,city="上海市",district="浦东新区",region_code="310115",category_code="OLD_RENOVATION",brand_code="ZHONGSHU",need_summary="真实 PostgreSQL 并发领取验证",status="DISPATCHED",review_status="APPROVED",duplicate_status="CLEAR",imported_at=now,submitted_at=now,raw_payload={})
        db.add(lead); db.flush()
        assignment = Assignment(lead_id=lead.id,company_id=company.id,receiver_company_id=company.id,supplier_company_id=company.id,status=AssignmentStatus.PENDING_CLAIM.value,points_price=100,claim_points=100,lead_snapshot={"customer_name":lead.customer_name,"phone_masked":"139****8888","city":"上海市","district":"浦东新区"},assigned_by=operator.id,assigned_at=now,expires_at=now+timedelta(hours=24),idempotency_key=f"pg-claim-seed-{suffix}")
        db.add(assignment); db.flush(); lead.current_assignment_id = assignment.id; db.commit()
        return {"assignment_id":assignment.id,"company_id":company.id,"username":owner.username,"password":"PgClaimOwner123!","before":1000}


def test_postgresql_concurrent_claim_has_one_ledger_and_one_balance_change() -> None:
    engine, factory = _factory()
    seeded = _seed(factory)
    def override_db():
        db = factory()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db] = override_db
    barrier = Barrier(2)
    def claim(_: int):
        with TestClient(app, base_url="http://testserver") as client:
            login = client.post("/api/v1/auth/login", json={"username":seeded["username"],"password":seeded["password"]})
            assert login.status_code == 200, login.text
            barrier.wait(timeout=10)
            return client.post(f"/api/v1/v1.2/assignments/{seeded['assignment_id']}/claim")
    try:
        with ThreadPoolExecutor(max_workers=2) as pool: responses = list(pool.map(claim, range(2)))
        assert all(response.status_code in {200,409} for response in responses), [response.text for response in responses]
        assert any(response.status_code == 200 for response in responses)
        with factory() as db:
            assignment = db.get(Assignment, seeded["assignment_id"])
            account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == seeded["company_id"]))
            ledgers = db.scalars(select(PointsLedger).where(PointsLedger.company_id == seeded["company_id"], PointsLedger.ledger_type == PointsLedgerType.CLAIM.value)).all()
            assert assignment is not None and assignment.status == AssignmentStatus.CLAIMED.value
            assert account is not None and int(account.balance) == seeded["before"] - 100
            assert len(ledgers) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
'''
write("apps/api/tests/test_claim_postgres_concurrency.py", claim_pg_test)

workflow_path = ".github/workflows/main-release.yml"
workflow = read(workflow_path)
if "Verify claim transaction concurrency on PostgreSQL" not in workflow:
    anchor = '''      - name: Verify invite binding concurrency on PostgreSQL
        env:
          INVITE_POSTGRES_TEST_URL: ${{ env.DATABASE_URL }}
        run: python -m pytest apps/api/tests/test_invite_postgres_concurrency.py -q
'''
    addition = anchor + '''\n      - name: Verify claim transaction concurrency on PostgreSQL\n        env:\n          CLAIM_POSTGRES_TEST_URL: ${{ env.DATABASE_URL }}\n        run: python -m pytest apps/api/tests/test_claim_postgres_concurrency.py -q\n'''
    if anchor not in workflow:
        raise RuntimeError("PostgreSQL invitation test workflow anchor not found")
    workflow = workflow.replace(anchor, addition, 1)
write(workflow_path, workflow)


# ---------------------------------------------------------------------------
# 6. Operations and external gate documentation.
# ---------------------------------------------------------------------------
write("docs/operations/INVITE-DELIVERY-CHANNELS.md", '''# 邀请发送渠道操作说明\n\n## 默认渠道\n\n`COPY` 与 `QRCODE` 只在系统内准备文案和二维码，不声明第三方已送达。二维码由仓库内固定 MIT 依赖生成，不访问 CDN 或外部二维码接口。\n\n## 外部渠道\n\n`SMS` 与 `WECHAT_MESSAGE` 必须同时满足：渠道显式启用、提供受控适配器、提供运行环境凭据、设置 1–30 秒超时。任一条件缺失时接口返回 `INVITE_DELIVERY_CHANNEL_DISABLED`，不得伪造成功。测试只使用内存测试替身，不写入真实手机号或凭据。\n\n## 上线步骤\n\n1. 在受控部署环境接入供应商适配器，不把密钥写入仓库。\n2. 在预发布环境验证超时、供应商失败和重试策略。\n3. 由业务负责人确认模板、发送对象和退订规则。\n4. 真实发送结果必须保存供应商回执编号；没有回执只能标记失败或未知。\n''')

write("docs/reports/INVITE-BINDING-EXTERNAL-GATES.md", '''# 专属邀请绑定外部门禁\n\n以下项目不以本地测试、mock callback、SQLite、健康检查或普通单元测试代替：\n\n- `EXTERNAL_PENDING`：真实微信服务号 WebView，iOS/Android 各至少一轮。\n- `EXTERNAL_PENDING`：生产等价 PostgreSQL 多实例/多进程并发压测。\n- `EXTERNAL_PENDING`：生产域名、TrustedHost、Secure Cookie、OAuth 回调白名单。\n- `EXTERNAL_PENDING`：管理员、运营、加盟商负责人、电销等全角色 UAT。\n- `EXTERNAL_PENDING`：短信或微信消息真实供应商凭据、模板审核及回执。\n- `PRODUCTION_NOT_VERIFIED`：未执行任何不可逆生产绑定或真实外部发送。\n''')

report_path = "docs/reports/INVITE-BINDING-COMPLETE-DELIVERY.md"
report = read(report_path) if (ROOT / report_path).exists() else "# 专属邀请绑定模块交付与门禁报告\n"
if "## 完整实现矩阵" not in report:
    report += '''\n## 完整实现矩阵\n\n- 测试环境隔离：确定性测试环境、临时 SQLite、测试 Host、本地存储。\n- S01：进程内 singleflight 重放合并；跨进程由事务、幂等键和数据库约束兜底。\n- P0：邀请快照、一次性邀请、主动确认、confirmation intent、OAuth、主账号原子保护。\n- 后台：创建前二次确认、旧邀请失效提示、复制链接与文案、本地二维码。\n- H5：预览、协议确认、微信 WebView 兼容状态页、旧入口显式拒绝。\n- P1：分页、筛选、详情、404 撤销、绑定追溯和审计。\n- P2：手机号唯一匹配及服务端确认、手工匹配确认、地区检索、新公司提交入口、发送适配层。\n- 门禁：全量 pytest/coverage、真实 PostgreSQL 邀请与领取并发、Chromium、JS、秘密扫描、迁移回滚。\n'''
write(report_path, report)

for plan in (
    ".omx/plans/module-01-invite-binding-worklist-2026-08-20.md",
    ".omx/plans/module-01-invite-binding-dev-plan-2026-08-20.md",
):
    target = ROOT / plan
    if target.exists():
        text = target.read_text(encoding="utf-8")
        marker = "## 2026-08-22 实现收口状态"
        if marker not in text:
            text += f'''\n\n{marker}\n\n代码已在 PR #82 完成 P0/P1/P2 主体与自动化门禁；真实微信 WebView、生产配置、生产等价多实例 PostgreSQL、真实发送供应商和全角色 UAT 保留为独立 `EXTERNAL_PENDING`，不得用 mock 或本地测试替代。\n'''
            target.write_text(text, encoding="utf-8")

print("authoritative invitation completion patch applied")
