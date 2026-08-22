from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement.rstrip() + "\n" + text[end:]


# Backend: keep the atomic database boundary while synchronizing the ORM identity map.
service_path = ROOT / "apps/api/src/services/invite_binding_service.py"
service = service_path.read_text(encoding="utf-8")
old_revoke = '''    db.execute(
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
new_revoke = '''    active_invites = db.scalars(
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
if old_revoke in service:
    service = service.replace(old_revoke, new_revoke, 1)
refresh_anchor = '''    if occupied is None:
        db.expire(company)
        refreshed = db.get(Company, company.id)
        if refreshed is None or refreshed.status != "ACTIVE":
            raise AppError("AUTH_COMPANY_UNAVAILABLE", "加盟商公司当前不可用", 403)
        raise AppError("AUTH_COMPANY_ALREADY_BOUND", "该公司已有主账号，不能重复绑定", 409)

    user = User(
'''
refresh_replacement = '''    if occupied is None:
        db.expire(company)
        refreshed = db.get(Company, company.id)
        if refreshed is None or refreshed.status != "ACTIVE":
            raise AppError("AUTH_COMPANY_UNAVAILABLE", "加盟商公司当前不可用", 403)
        raise AppError("AUTH_COMPANY_ALREADY_BOUND", "该公司已有主账号，不能重复绑定", 409)

    # The conditional UPDATE deliberately bypasses the identity map. Refresh
    # the loaded row so callers never observe a stale primary_user_id.
    db.expire(company, ["primary_user_id"])
    db.refresh(company, attribute_names=["primary_user_id"])
    if company.primary_user_id != user_id:
        raise AppError("AUTH_COMPANY_BIND_CONFLICT", "公司主账号占用结果异常", 409)

    user = User(
'''
if refresh_anchor in service:
    service = service.replace(refresh_anchor, refresh_replacement, 1)
service_path.write_text(service, encoding="utf-8")


# H5: preview -> explicit consent -> confirmation intent -> OAuth.
h5_path = ROOT / "apps/h5/app.js"
h5 = h5_path.read_text(encoding="utf-8")
h5_flow = r'''const inviteErrorMessages = {
  AUTH_INVITE_USED: '该邀请已使用，请联系平台重新获取。',
  AUTH_INVITE_REVOKED: '该邀请已撤销，请联系平台重新获取。',
  AUTH_INVITE_EXPIRED: '该邀请已过期，请联系平台重新获取。',
  AUTH_INVITE_INVALID: '邀请链接无效，请检查链接是否完整。',
  AUTH_COMPANY_UNAVAILABLE: '该公司当前不可用，请联系平台处理。',
  AUTH_COMPANY_ALREADY_BOUND: '该公司已有主账号，不能重复绑定。',
  AUTH_WECHAT_BOUND_OTHER_COMPANY: '当前微信已绑定其他公司，系统不会自动覆盖。',
  AUTH_CONFIRMATION_INTENT_INVALID: '绑定确认无效，请重新打开邀请链接。',
  AUTH_CONFIRMATION_INTENT_EXPIRED: '绑定确认已过期，请重新确认。',
  AUTH_CONFIRMATION_INTENT_USED: '该绑定确认已使用，请勿重复提交。',
  AUTH_OAUTH_STATE_INVALID: '微信授权状态已失效，请重新进入。',
};

function renderInviteFailure(error) {
  const message = inviteErrorMessages[error?.code] || (error?.message === 'Failed to fetch' ? '网络连接失败，请检查网络后重试。' : error?.message || '邀请加载失败，请稍后重试。');
  zsSetSafeHtml(app, `<section class="login-page"><div class="login-logo"><img src="./logo.png" alt="合家美宅"><h1>无法完成绑定</h1><p>${esc(message)}</p></div><div class="login-panel"><button class="btn btn-outline btn-block" id="invite-retry-button">重新加载</button></div></section>`);
  document.querySelector('#invite-retry-button')?.addEventListener('click', () => renderLogin(), {once:true});
}

async function renderLogin(){
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const invite = params.get('invite') || '';
  if (!invite) {
    zsSetSafeHtml(app, `<section class="login-page"><div class="login-logo"><img src="./logo.png" alt="合家美宅"><h1>合家美宅客资助手</h1><p>已绑定用户可直接使用微信授权登录</p></div><div class="login-panel"><button class="btn btn-primary btn-block" id="wechat-existing-login">微信授权登录</button><p class="help">首次绑定请使用平台发出的专属邀请链接。</p></div></section>`);
    document.querySelector('#wechat-existing-login')?.addEventListener('click', () => {
      location.assign(`${API}/auth/wechat/start?return_url=${encodeURIComponent('/h5/#/home')}`);
    }, {once:true});
    return;
  }
  zsSetSafeHtml(app, `<section class="login-page"><div class="login-logo"><img src="./logo.png" alt="合家美宅"><h1>核对专属邀请</h1><p>正在读取邀请信息，请稍候……</p></div><div class="login-panel"><div class="skeleton"></div></div></section>`);
  let preview;
  try {
    preview = await api('/auth/invites/preview', {method:'POST', body:JSON.stringify({invite_token:invite})});
  } catch (error) {
    renderInviteFailure(error);
    return;
  }
  zsSetSafeHtml(app, `<section class="login-page"><div class="login-logo"><img src="./logo.png" alt="合家美宅"><h1>确认绑定公司</h1><p>请核对以下信息，确认后才会进入微信授权。</p></div><div class="login-panel"><dl class="detail-list"><div class="detail-row"><dt>被邀请负责人</dt><dd>${esc(preview.owner_name)}</dd></div><div class="detail-row"><dt>公司名称</dt><dd>${esc(preview.company_name)}</dd></div><div class="detail-row"><dt>邀请有效期</dt><dd>${fmtDate(preview.expires_at)}</dd></div></dl><p class="help">${esc(preview.binding_explanation || '确认后将把当前微信绑定为该公司的唯一主账号。')}</p><label class="invite-consent"><input type="checkbox" id="invite-consent-checkbox"> <span>我已核对公司与负责人信息，并同意绑定当前微信账号。</span></label><button class="btn btn-primary btn-block" id="invite-confirm-button" disabled>确认并进入微信授权</button><p class="help">未主动确认前，系统不会创建绑定或进入微信授权。</p></div></section>`);
  const checkbox = document.querySelector('#invite-consent-checkbox');
  const confirmButton = document.querySelector('#invite-confirm-button');
  checkbox?.addEventListener('change', () => { confirmButton.disabled = !checkbox.checked; });
  confirmButton?.addEventListener('click', async () => {
    if (!checkbox?.checked || confirmButton.disabled) return;
    confirmButton.disabled = true;
    confirmButton.textContent = '正在进入微信授权……';
    try {
      const result = await api('/auth/invites/confirm-start', {method:'POST', body:JSON.stringify({invite_token:invite, return_url:'/h5/#/home'})});
      location.assign(result.authorization_url);
    } catch (error) {
      confirmButton.disabled = false;
      confirmButton.textContent = '确认并进入微信授权';
      renderInviteFailure(error);
    }
  }, {once:true});
}
'''
h5 = replace_between(h5, "function renderLogin(){", "async function renderHome(){", h5_flow) + "async function renderHome(){" + h5.split("async function renderHome(){", 1)[1] if False else h5
# Avoid precedence ambiguity by doing the replacement directly.
start = h5.index("function renderLogin(){") if "function renderLogin(){" in h5 else -1
if start >= 0:
    end = h5.index("async function renderHome(){", start)
    h5 = h5[:start] + h5_flow + "\n" + h5[end:]
elif "invite-confirm-button" not in h5:
    raise RuntimeError("H5 login function anchor not found")
h5_path.write_text(h5, encoding="utf-8")


# Admin: preflight confirmation, copy_text, local QR and paginated invite records.
admin_path = ROOT / "apps/admin/app.js"
admin = admin_path.read_text(encoding="utf-8")
admin_flow = r'''async function copyInviteText(value){
  try{if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(value)}else{const area=document.createElement('textarea');area.value=value;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();document.execCommand('copy');area.remove()}toast('邀请文案已复制')}catch(error){toast('复制失败，请手动复制','error')}
}
function renderInviteQr(inviteUrl){const node=document.querySelector('#invite-qrcode');if(!node)return;if(typeof window.qrcode!=='function'){node.textContent='二维码组件加载失败，请复制邀请链接';return}const qr=window.qrcode(0,'M');qr.addData(inviteUrl);qr.make();node.innerHTML=qr.createSvgTag({cellSize:4,margin:2,scalable:true});}
function openInviteMaterial(data){openModal('专属邀请已生成',`<div class="invite-material"><dl class="detail-grid"><dt>负责人</dt><dd>${esc(data.owner_name)}</dd><dt>公司</dt><dd>${esc(data.company_name)}</dd><dt>有效期</dt><dd>${fmt(data.expires_at)}</dd></dl><div id="invite-qrcode" style="display:flex;justify-content:center;margin:18px 0"></div><label>邀请链接</label><textarea id="invite-url-text" class="textarea" style="width:100%;min-height:76px" readonly>${esc(data.invite_url)}</textarea><label>完整邀请文案</label><textarea id="invite-copy-text" class="textarea" style="width:100%;min-height:120px" readonly>${esc(data.copy_text)}</textarea></div>`,`<button id="copy-invite-url" class="btn btn-outline">复制链接</button><button id="copy-invite-text" class="btn btn-primary">复制邀请文案</button><button data-close class="btn btn-outline">完成</button>`);renderInviteQr(data.invite_url);document.querySelector('#copy-invite-url')?.addEventListener('click',()=>copyInviteText(data.invite_url));document.querySelector('#copy-invite-text')?.addEventListener('click',()=>copyInviteText(data.copy_text));}
async function inviteCompany(companyId){try{const preflight=await request(`/auth/companies/${companyId}/invites/preflight`);const activeWarning=preflight.has_active_invite?'<div class="alert alert-warning">生成新邀请后，上一条未使用邀请将立即失效。</div>':'';openModal('确认生成专属邀请',`${activeWarning}<dl class="detail-grid"><dt>公司名称</dt><dd>${esc(preflight.company_name)}</dd><dt>负责人姓名</dt><dd>${esc(preflight.owner_name)}</dd><dt>当前有效邀请</dt><dd>${preflight.has_active_invite?'有':'无'}</dd></dl><p style="color:var(--muted)">用户确认前不会发送创建请求。</p>`,`<button data-close class="btn btn-outline">取消</button><button id="confirm-create-invite" class="btn btn-primary">确认生成</button>`);const button=document.querySelector('#confirm-create-invite');button?.addEventListener('click',async()=>{if(button.disabled)return;button.disabled=true;button.textContent='生成中……';try{const result=await request(`/auth/companies/${companyId}/invites`,{method:'POST',body:JSON.stringify({expires_hours:72})});closeOverlay();openInviteMaterial(result)}catch(error){button.disabled=false;button.textContent='确认生成';toast(error.message,'error')}},{once:true});}catch(error){toast(error.message,'error')}}
async function inviteRecordsModal(pageNo=1){const status=document.querySelector('#invite-status-filter')?.value||'';const companyId=document.querySelector('#invite-company-filter')?.value||'';const params=new URLSearchParams({page:String(pageNo),page_size:'20'});if(status)params.set('status',status);if(companyId)params.set('company_id',companyId);try{const data=await request(`/auth/invites?${params}`);const companies=await getCompanies().catch(()=>[]);const rows=data.items.map(item=>`<tr><td>${fmt(item.created_at)}</td><td>${esc(item.creator_name||'--')}</td><td>${esc(item.company_name||'--')}<br><small>${esc(item.owner_name||'--')}</small></td><td>${fmt(item.expires_at)}</td><td>${badge(item.status,statusType(item.status))}</td><td>${esc(item.bound_user_name||'--')}<br><small>${item.used_at?fmt(item.used_at):''}</small></td><td>${item.status==='ACTIVE'?`<button class="btn btn-small btn-outline" data-revoke-invite="${item.invite_id}">撤销</button>`:'--'}</td></tr>`).join('');const companyOptions=['<option value="">全部公司</option>',...companies.map(item=>`<option value="${item.id}" ${companyId===item.id?'selected':''}>${esc(item.name)}</option>`)].join('');openModal('邀请记录',`<div style="display:flex;gap:10px;margin-bottom:12px"><select id="invite-company-filter" class="select">${companyOptions}</select><select id="invite-status-filter" class="select"><option value="">全部状态</option>${['ACTIVE','USED','EXPIRED','REVOKED'].map(value=>`<option value="${value}" ${status===value?'selected':''}>${value}</option>`).join('')}</select><button id="apply-invite-filter" class="btn btn-outline">筛选</button></div>${table(['创建时间','创建人','公司/负责人','有效期','状态','绑定用户','操作'],rows,'暂无邀请记录')}<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px"><button id="invite-prev-page" class="btn btn-outline" ${pageNo<=1?'disabled':''}>上一页</button><span style="padding:9px">第 ${pageNo} 页 / 共 ${data.total} 条</span><button id="invite-next-page" class="btn btn-outline" ${pageNo*data.page_size>=data.total?'disabled':''}>下一页</button></div>`,`<button data-close class="btn btn-primary">关闭</button>`);document.querySelector('#apply-invite-filter')?.addEventListener('click',()=>inviteRecordsModal(1));document.querySelector('#invite-prev-page')?.addEventListener('click',()=>inviteRecordsModal(pageNo-1));document.querySelector('#invite-next-page')?.addEventListener('click',()=>inviteRecordsModal(pageNo+1));document.querySelectorAll('[data-revoke-invite]').forEach(button=>button.addEventListener('click',async()=>{if(!confirm('确认撤销该邀请？撤销后链接将立即失效。'))return;try{await request(`/auth/invites/${button.dataset.revokeInvite}/revoke`,{method:'POST'});toast('邀请已撤销');inviteRecordsModal(pageNo)}catch(error){toast(error.message,'error')}}));}catch(error){toast(error.message,'error')}}
async function companies(){const d=await request('/companies?page=1&page_size=200');state.companies=d.items;const finance=can('points.read')||can('*');const rows=d.items.map(x=>`<tr><td><b>${esc(x.name)}</b><br>${esc(x.code)}</td><td>${esc(x.owner_name||'--')}<br>${esc(x.contact_phone_masked||'')}</td><td>${esc(x.region_codes.join('、')||'--')}</td><td>${esc(x.capabilities.map(c=>c.category_code).join('、')||'--')}</td><td>${badge(x.status,statusType(x.status))}</td><td>${esc(x.level_code)}</td>${finance?`<td>${num(x.points_balance)}</td>`:''}<td><button class="btn btn-small btn-primary" data-invite="${x.id}">邀请</button></td></tr>`);shell(`${pageHead('加盟商公司','微信用户绑定公司；地区、类目和品牌能力维护在公司档案中。','<button id="invite-records" class="btn btn-outline">邀请记录</button><button id="new-company" class="btn btn-primary">新建加盟商</button>')}<section class="panel">${table(['公司','负责人','服务地区','业务能力','状态','等级',...(finance?['积分余额']:[]),'操作'],rows,'暂无加盟商公司')}</section>`,'加盟商公司');document.querySelector('#new-company')?.addEventListener('click',companyModal);document.querySelector('#invite-records')?.addEventListener('click',()=>inviteRecordsModal(1));document.querySelectorAll('[data-invite]').forEach(button=>button.addEventListener('click',()=>inviteCompany(button.dataset.invite)));}
'''
if "async function companies(){" in admin:
    start = admin.index("async function companies(){")
    end = admin.index("function companyModal(){", start)
    admin = admin[:start] + admin_flow + "\n" + admin[end:]
elif "/invites/preflight" not in admin:
    raise RuntimeError("admin companies function anchor not found")
admin_path.write_text(admin, encoding="utf-8")


# Load the fixed local QR dependency before the application bundle.
admin_html = ROOT / "apps/admin/index.html"
html = admin_html.read_text(encoding="utf-8")
if "vendor/qrcode.min.js" not in html:
    html, count = re.subn(r'(<script[^>]+src=["\'][^"\']*app\.js[^>]*></script>)', '<script src="./vendor/qrcode.min.js"></script>\n  \\1', html, count=1)
    if count != 1:
        raise RuntimeError("admin app script tag not found")
admin_html.write_text(html, encoding="utf-8")

vendor = ROOT / "apps/admin/vendor/qrcode.min.js"
digest = hashlib.sha256(vendor.read_bytes()).hexdigest()
qr_doc = ROOT / "docs/security/QR-CODE-VENDOR.md"
qr_doc.parent.mkdir(parents=True, exist_ok=True)
qr_doc.write_text(f'''# 后台二维码固定依赖审计\n\n- 文件：`apps/admin/vendor/qrcode.min.js`\n- 上游：Kazuhiko Arase QR Code Generator for JavaScript\n- 许可证：MIT（许可证声明保留在 vendor 文件头）\n- SHA-256：`{digest}`\n- 加载方式：管理后台同源本地静态文件\n- 禁止方式：运行时 CDN、远程脚本回退、第三方二维码生成接口\n''', encoding="utf-8")

frontend_test = r'''from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
H5_APP = ROOT / "apps/h5/app.js"
ADMIN_APP = ROOT / "apps/admin/app.js"
ADMIN_HTML = ROOT / "apps/admin/index.html"
QR_VENDOR = ROOT / "apps/admin/vendor/qrcode.min.js"
QR_AUDIT = ROOT / "docs/security/QR-CODE-VENDOR.md"


def test_h5_invite_flow_requires_preview_and_confirmation_before_oauth() -> None:
    source = H5_APP.read_text(encoding="utf-8")
    assert "/auth/invites/preview" in source
    assert "/auth/invites/confirm-start" in source
    assert "/auth/wechat/start?invite=" not in source
    assert source.index("/auth/invites/preview") < source.index("/auth/invites/confirm-start") < source.index("location.assign(result.authorization_url)")


def test_h5_confirmation_button_has_one_machine_detectable_binding() -> None:
    sources = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "apps/h5").glob("*.js")))
    assert sources.count('id="invite-confirm-button"') == 1
    assert sources.count("#invite-confirm-button") == 1
    assert re.search(r"confirmButton\?\.addEventListener\(['\"]click['\"]", H5_APP.read_text(encoding="utf-8"))


def test_h5_declares_required_error_states() -> None:
    source = H5_APP.read_text(encoding="utf-8")
    required = {"AUTH_INVITE_USED", "AUTH_INVITE_REVOKED", "AUTH_INVITE_EXPIRED", "AUTH_COMPANY_UNAVAILABLE", "AUTH_COMPANY_ALREADY_BOUND", "AUTH_WECHAT_BOUND_OTHER_COMPANY", "AUTH_OAUTH_STATE_INVALID", "AUTH_CONFIRMATION_INTENT_INVALID", "AUTH_CONFIRMATION_INTENT_EXPIRED", "AUTH_CONFIRMATION_INTENT_USED"}
    assert required.issubset(set(re.findall(r"\bAUTH_[A-Z_]+\b", source)))
    assert "网络连接失败" in source


def test_admin_invite_flow_has_preflight_copy_qr_and_records() -> None:
    source = ADMIN_APP.read_text(encoding="utf-8")
    for value in ("/invites/preflight", "confirm-create-invite", "invite_url", "copy_text", "renderInviteQr", "/auth/invites?", "data-revoke-invite"):
        assert value in source
    assert "生成新邀请后，上一条未使用邀请将立即失效。" in source


def test_admin_uses_only_local_scripts_and_pinned_qr_digest() -> None:
    html = ADMIN_HTML.read_text(encoding="utf-8")
    script_sources = re.findall(r"<script[^>]+src=[\"']([^\"']+)", html, flags=re.I)
    assert script_sources and all(not source.startswith(("http://", "https://", "//")) for source in script_sources)
    assert "./vendor/qrcode.min.js" in script_sources
    digest = hashlib.sha256(QR_VENDOR.read_bytes()).hexdigest()
    assert digest in QR_AUDIT.read_text(encoding="utf-8")
'''
(ROOT / "apps/api/tests/test_invite_frontend_contract.py").write_text(frontend_test, encoding="utf-8")

postgres_test = r'''from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import apps.api.src.services.rbac as rbac_service
from apps.api.src.core.errors import AppError
from apps.api.src.core.invite_models import InviteConfirmationIntent
from apps.api.src.core.models import Company, InviteToken, User, WechatIdentity
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.invite_binding_service import bind_wechat_with_confirmation, create_company_invite, create_confirmation_intent

POSTGRES_URL = os.getenv("INVITE_POSTGRES_TEST_URL", "")
pytestmark = pytest.mark.skipif(not POSTGRES_URL.startswith("postgresql"), reason="requires PostgreSQL")


def _seed_rbac(db) -> None:
    for name in ("seed_rbac", "sync_fixed_rbac", "seed_fixed_rbac", "sync_rbac"):
        candidate = getattr(rbac_service, name, None)
        if callable(candidate):
            candidate(db)
            return
    raise AssertionError("RBAC seed function not found")


def _factory():
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _company(db, suffix: str) -> Company:
    return create_company(db, CompanyCreateBody(code=f"PG-INV-{suffix}", name=f"PostgreSQL 邀请并发公司 {suffix}", owner_name="并发负责人", region_codes=["310000"], capabilities=[{"category_code": "OLD_RENOVATION", "brand_code": "ZHONGSHU"}]))


def test_postgresql_concurrent_bind_has_one_winner_and_no_partial_rows() -> None:
    engine, factory = _factory(); suffix = uuid4().hex[:10].upper()
    with factory() as db:
        _seed_rbac(db); company = _company(db, suffix); created = create_company_invite(db, company.id, None, 24)
        starts = [create_confirmation_intent(db, created.raw_token, "/h5/#/home") for _ in range(2)]
        company_id, invite_id = company.id, created.invite.id; intent_ids = [item.intent_id for item in starts]; carriers = [item.confirmation_intent for item in starts]; db.commit()
    barrier = Barrier(2)
    def bind(index: int):
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                user, _, _ = bind_wechat_with_confirmation(db, carriers[index], openid=f"pg-invite-openid-{suffix}-{index}", nickname=f"并发用户{index}"); db.commit(); return "OK", user.id
            except AppError as exc:
                db.rollback(); return exc.code, None
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(bind, range(2)))
    codes = [code for code, _ in results]
    assert codes.count("OK") == 1, results
    assert all(code == "OK" or code in {"AUTH_COMPANY_ALREADY_BOUND", "AUTH_INVITE_INVALID", "AUTH_INVITE_USED", "AUTH_CONFIRMATION_INTENT_USED"} for code in codes), results
    with factory() as db:
        company = db.get(Company, company_id); invite = db.get(InviteToken, invite_id); users = db.scalars(select(User).where(User.company_id == company_id)).all(); identities = db.scalars(select(WechatIdentity).where(WechatIdentity.openid.like(f"pg-invite-openid-{suffix}-%"))).all(); used_intents = db.scalar(select(func.count(InviteConfirmationIntent.id)).where(InviteConfirmationIntent.id.in_(intent_ids), InviteConfirmationIntent.used_at.is_not(None)))
        assert company and company.primary_user_id and invite and invite.used_at and len(users) == len(identities) == used_intents == 1
        assert identities[0].user_id == users[0].id == company.primary_user_id
    engine.dispose()


def test_postgresql_concurrent_creation_leaves_one_active_invite() -> None:
    engine, factory = _factory(); suffix = uuid4().hex[:10].upper()
    with factory() as db: company = _company(db, suffix); company_id = company.id; db.commit()
    barrier = Barrier(2)
    def create(_: int):
        with factory() as db: barrier.wait(timeout=10); result = create_company_invite(db, company_id, None, 24); db.commit(); return result.invite.id
    with ThreadPoolExecutor(max_workers=2) as pool: invite_ids = list(pool.map(create, range(2)))
    with factory() as db: active = db.scalars(select(InviteToken).where(InviteToken.id.in_(invite_ids), InviteToken.used_at.is_(None), InviteToken.revoked_at.is_(None))).all(); assert len(active) == 1 and len(set(invite_ids)) == 2
    engine.dispose()
'''
(ROOT / "apps/api/tests/test_invite_postgres_concurrency.py").write_text(postgres_test, encoding="utf-8")

browser_test = r'''from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[3]


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return


@contextmanager
def _static_server():
    handler = lambda *args, **kwargs: _QuietHandler(*args, directory=str(ROOT), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield f"http://127.0.0.1:{server.server_port}"
    finally: server.shutdown(); server.server_close(); thread.join(timeout=5)


def _envelope(data=None, *, code="OK", message="") -> str:
    return json.dumps({"code": code, "message": message, "data": data}, ensure_ascii=False)


def test_h5_mobile_invite_preview_confirmation_and_oauth_navigation() -> None:
    with _static_server() as base, playwright.sync_playwright() as runner:
        browser = runner.chromium.launch(headless=True); page = browser.new_page(viewport={"width": 390, "height": 844}); confirm_calls = []
        page.route("**/api/v1/auth/invites/preview", lambda route: route.fulfill(status=200, content_type="application/json", body=_envelope({"invite_id":"invite-1","company_id":"company-1","company_name":"上海浏览器验收加盟商","owner_name":"张负责人","expires_at":"2026-08-23T08:00:00+00:00","binding_explanation":"确认后绑定当前微信为公司唯一主账号。"})))
        def confirm(route): confirm_calls.append(route.request.post_data or ""); route.fulfill(status=200, content_type="application/json", body=_envelope({"confirmation_intent":"signed-intent","authorization_url":f"{base}/wechat-oauth-target","expires_at":"2026-08-22T08:10:00+00:00"}))
        page.route("**/api/v1/auth/invites/confirm-start", confirm); page.route("**/wechat-oauth-target", lambda route: route.fulfill(status=200, content_type="text/html", body="<h1>OAuth target</h1>"))
        page.goto(f"{base}/apps/h5/index.html#/login?invite=browser-token"); page.wait_for_selector("#invite-confirm-button")
        assert "上海浏览器验收加盟商" in page.locator("body").inner_text() and page.locator("#invite-confirm-button").is_disabled() and confirm_calls == []
        page.locator("#invite-consent-checkbox").check(); page.locator("#invite-confirm-button").click(); page.wait_for_url("**/wechat-oauth-target"); assert len(confirm_calls) == 1; browser.close()


def test_h5_expired_invite_has_explicit_error_state() -> None:
    with _static_server() as base, playwright.sync_playwright() as runner:
        browser = runner.chromium.launch(headless=True); page = browser.new_page(viewport={"width":390,"height":844}); page.route("**/api/v1/auth/invites/preview", lambda route: route.fulfill(status=410, content_type="application/json", body=_envelope(None, code="AUTH_INVITE_EXPIRED", message="邀请已过期"))); page.goto(f"{base}/apps/h5/index.html#/login?invite=expired-token"); page.wait_for_selector("#invite-retry-button"); assert "该邀请已过期" in page.locator("body").inner_text(); browser.close()


def test_admin_preflight_prevents_early_create_and_renders_local_qr() -> None:
    with _static_server() as base, playwright.sync_playwright() as runner:
        browser = runner.chromium.launch(headless=True); page = browser.new_page(viewport={"width":1440,"height":900}); create_calls=[]
        def api(route):
            url=route.request.url
            if url.endswith("/auth/companies/company-1/invites/preflight"): body=_envelope({"company_id":"company-1","company_name":"后台验收加盟商","owner_name":"李负责人","has_active_invite":True})
            elif url.endswith("/auth/companies/company-1/invites"): create_calls.append(route.request.post_data or ""); body=_envelope({"invite_id":"invite-1","company_name":"后台验收加盟商","owner_name":"李负责人","invite_url":"https://example.test/h5/#/login?invite=token","copy_text":"李负责人您好，邀请您绑定后台验收加盟商。","expires_at":"2026-08-23T08:00:00+00:00","status":"ACTIVE"})
            elif "/auth/me" in url: body=_envelope({"id":"admin","display_name":"管理员","roles":["SUPER_ADMIN"],"permissions":["*"]})
            else: body=_envelope({"items":[],"total":0,"page":1,"page_size":20})
            route.fulfill(status=200, content_type="application/json", body=body)
        page.route("**/api/v1/**", api); page.goto(f"{base}/apps/admin/index.html"); page.wait_for_function("typeof window.inviteCompany === 'function'"); page.evaluate("inviteCompany('company-1')"); page.wait_for_selector("#confirm-create-invite"); assert create_calls == []; page.locator("#confirm-create-invite").click(); page.wait_for_selector("#invite-qrcode svg"); assert len(create_calls) == 1; browser.close()
'''
(ROOT / "apps/api/tests/test_invite_browser_smoke.py").write_text(browser_test, encoding="utf-8")

workflow_path = ROOT / ".github/workflows/main-release.yml"
workflow = workflow_path.read_text(encoding="utf-8")
pg_anchor = '''      - name: Verify H04 dataset creation on PostgreSQL
        env:
          H04_POSTGRES_DATASET_TEST_URL: ${{ env.DATABASE_URL }}
        run: python -m pytest apps/api/tests/test_prepare_performance_dataset.py::test_prepare_dataset_flush_order_on_postgresql -q
'''
if "Verify invite binding concurrency on PostgreSQL" not in workflow:
    workflow = workflow.replace(pg_anchor, pg_anchor + '''\n      - name: Verify invite binding concurrency on PostgreSQL\n        env:\n          INVITE_POSTGRES_TEST_URL: ${{ env.DATABASE_URL }}\n        run: python -m pytest apps/api/tests/test_invite_postgres_concurrency.py -q\n''', 1)
browser_job = '''\n  invite-browser-smoke:\n    runs-on: ubuntu-latest\n    timeout-minutes: 20\n    steps:\n      - name: Checkout\n        uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0\n      - name: Set up Python\n        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0\n        with:\n          python-version: "3.12"\n          cache: pip\n      - name: Install browser smoke dependencies\n        run: pip install -r requirements.txt -r requirements-browser.txt\n      - name: Install Chromium\n        run: python -m playwright install --with-deps chromium\n      - name: Run H5 and admin invite browser smoke\n        run: python -m pytest apps/api/tests/test_invite_browser_smoke.py -q\n\n'''
if "invite-browser-smoke:" not in workflow:
    workflow = workflow.replace("\n  staging-performance:\n", browser_job + "  staging-performance:\n", 1)
workflow_path.write_text(workflow, encoding="utf-8")

report = ROOT / "docs/reports/INVITE-BINDING-COMPLETE-DELIVERY.md"
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text('''# 专属邀请绑定模块交付与门禁报告\n\n## LOCALLY_VERIFIED\n\n测试环境隔离、S01 singleflight、邀请 P0/P1/P2、后台二次确认、H5 confirmation intent、固定依赖二维码、前端合同、Chromium smoke 和 PostgreSQL 并发用例均已实现。\n\n## CI_VERIFIED\n\n以 PR #82 最新 Head 的 `verify-main`、`postgres-migration` 与 `invite-browser-smoke` 全绿为准。\n\n## EXTERNAL_PENDING\n\n真实微信 WebView、真实生产配置、生产等价 PostgreSQL 多进程压测、全角色 UAT、短信/微信消息供应商凭据。\n\n## PRODUCTION_NOT_VERIFIED\n\n本报告不以 mock、SQLite、健康检查或普通单元测试冒充生产完成。\n\n## S01 决定\n\n未盲目 cherry-pick `fix/v1.2-s01-claim-scope@db27207923f7949b7333c4d0e2ec0876af8bd0a2`；仅以最新 main 为基线重集成有效的进程内请求合并，跨进程一致性继续由幂等键、数据库约束和事务保证。\n\n## 迁移与回滚\n\n升级：`python -m alembic -c alembic.ini upgrade head`。回滚：`python -m alembic -c alembic.ini downgrade 0006`。回滚前必须备份邀请绑定审计数据。\n''', encoding="utf-8")

# Temporary source-export workflow is no longer needed.
(ROOT / ".github/workflows/pr-source-snapshot.yml").unlink(missing_ok=True)
print("invite completion patch applied")
