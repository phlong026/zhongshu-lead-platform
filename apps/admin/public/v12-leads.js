import {request,query} from './api.js';
import {closeOverlay,esc,fmt,openDrawer,openModal,toast} from './ui.js';

const app=document.querySelector('#app');
const state={
  me:null,
  tab:'platform',
  platformItems:[],
  supplierItems:[],
  cities:[],
  districts:[],
  platformStatus:'',
  supplierReviewStatus:'PENDING'
};
const can=code=>state.me?.permissions?.includes('*')||state.me?.permissions?.includes(code);
const labels={DRAFT:'草稿',PENDING_REVIEW:'待资料初审',READY_DISPATCH:'待人工派发',DUPLICATE:'疑似重复',INVALID:'无效',CLOSED:'已关闭',APPROVED:'已通过',REJECTED:'已驳回',PENDING:'待审核',CLEAR:'无重复',HARD_DUPLICATE:'90天内已有相同客户',REWARD_DUPLICATE:'近期已发放奖励',HISTORICAL_SUSPECT:'历史记录疑似重复',OVERRIDDEN:'已确认不重复'};
const statusClass=value=>({READY_DISPATCH:'ok',APPROVED:'ok',CLEAR:'ok',OVERRIDDEN:'blue',DRAFT:'',PENDING_REVIEW:'warn',PENDING:'warn',DUPLICATE:'warn',HARD_DUPLICATE:'bad',HISTORICAL_SUSPECT:'warn',INVALID:'bad',REJECTED:'bad'}[value]||'');
const badge=value=>`<span class="v12-badge ${statusClass(value)}">${esc(labels[value]||value||'--')}</span>`;
const icon=name=>window.ZSIconSystem?.svg?.(name)||'';
const value=id=>document.querySelector(id)?.value?.trim()||'';

function shell(content=''){
  zsSetSafeHtml(app, `<div class="v12-shell"><header class="v12-topbar"><div class="v12-brand"><img src="./logo.png" alt="合家美宅"><div><strong>客资录入与初审</strong><small>平台录入 · 加盟商客资初审</small></div></div><div class="v12-top-actions"><a class="v12-btn" href="./#/dashboard">${icon('chevron-left')}返回工作台首页</a></div></header><main class="v12-main"><section class="v12-hero"><div class="v12-hero-icon">${icon('inbox')}</div><div><h1>录入客资，审核加盟商提交的信息</h1><p>系统会自动检查信息是否完整、已获得客户授权，以及是否存在重复记录。</p></div></section><nav class="v12-tabs">${can('lead.manual.manage')?`<button class="v12-tab ${state.tab==='platform'?'active':''}" data-tab="platform">${icon('inbox')}平台录入</button>`:''}${can('lead.supplier.review')?`<button class="v12-tab ${state.tab==='supplier'?'active':''}" data-tab="supplier">${icon('user-check')}加盟商客资初审</button>`:''}</nav><div id="workspace">${content}</div></main></div>`);
  document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>{state.tab=button.dataset.tab;renderCurrent();});
}

function showLoading(){document.querySelector('#workspace').innerHTML='<div class="v12-panel v12-loading">正在加载数据…</div>';}
function fail(error){console.error(error);zsSetSafeHtml(document.querySelector('#workspace'), `<div class="v12-error"><b>页面加载失败</b><div style="margin-top:8px">${esc(error.message||'未知错误')}</div></div>`);toast(error.message||'页面加载失败','error');}
function table(headers,rows,emptyText){return rows.length?`<div class="v12-table-wrap"><table class="v12-table"><thead><tr>${headers.map(item=>`<th>${esc(item)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`:`<div class="v12-empty"><b>${icon('search')}</b>${esc(emptyText)}</div>`;}

async function boot(){
  try{
    state.me=await request('/auth/me');
    if(!can('lead.manual.manage')&&!can('lead.supplier.review'))throw new Error('当前账号无权访问客资供给工作台');
    state.tab=can('lead.manual.manage')?'platform':'supplier';
    shell();
    await renderCurrent();
  }catch(error){
    if(error.code==='AUTH_REQUIRED'||error.code==='AUTH_INVALID'){location.href='./#/dashboard';return;}
    zsSetSafeHtml(app, `<main class="v12-main"><div class="v12-error">${esc(error.message||'无法进入工作台')}</div><p><a class="v12-btn" href="./#/dashboard">返回工作台首页</a></p></main>`);
  }
}

async function renderCurrent(){shell();showLoading();try{if(state.tab==='supplier')await renderSupplierQueue();else await renderPlatformLeads();}catch(error){fail(error);}}

async function renderPlatformLeads(){
  const data=await request('/v1.2/platform/leads'+query({page:1,page_size:200,status:state.platformStatus}));
  state.platformItems=data.items||[];
  const stats={all:data.total||0,draft:state.platformItems.filter(item=>item.status==='DRAFT').length,ready:state.platformItems.filter(item=>item.status==='READY_DISPATCH').length,duplicate:state.platformItems.filter(item=>item.status==='DUPLICATE').length};
  const rows=state.platformItems.map(item=>{
    const ownsDraft=can('*')||item.submitter_user_id===state.me.id;
    const mutationActions=item.status==='DRAFT'&&ownsDraft?`<button class="v12-btn small" data-edit="${item.id}">编辑</button><button class="v12-btn small primary" data-submit="${item.id}">提交</button>`:'';
    return `<tr><td class="v12-customer"><strong>${esc(item.customer_name)}</strong><span>${icon('phone')}${esc(item.phone_masked||'--')}</span></td><td>${esc(item.city||'--')} ${esc(item.district||'')}</td><td>${esc(item.source_channel||'--')}</td><td>${badge(item.status)}<div style="margin-top:6px">${badge(item.duplicate_status)}</div></td><td>${fmt(item.submitted_at||item.created_at)}</td><td><div class="v12-actions"><button class="v12-btn small" data-detail="${item.id}">详情</button>${mutationActions}</div></td></tr>`;
  });
  zsSetSafeHtml(document.querySelector('#workspace'), `<section class="v12-summary"><div class="v12-stat"><i>${icon('list')}</i><span>当前结果</span><strong>${stats.all}</strong></div><div class="v12-stat"><i>${icon('file-text')}</i><span>草稿</span><strong>${stats.draft}</strong></div><div class="v12-stat"><i>${icon('hand-claim')}</i><span>待人工派发</span><strong>${stats.ready}</strong></div><div class="v12-stat"><i>${icon('alert-triangle')}</i><span>重复/疑似</span><strong>${stats.duplicate}</strong></div></section><section class="v12-panel"><div class="v12-toolbar"><div class="v12-toolbar-left"><h2>平台录入客资</h2><select class="v12-select" id="platform-status"><option value="">全部状态</option>${['DRAFT','READY_DISPATCH','DUPLICATE','INVALID','CLOSED'].map(option=>`<option value="${option}" ${state.platformStatus===option?'selected':''}>${esc(labels[option])}</option>`).join('')}</select><button class="v12-btn" id="platform-filter">${icon('search')}查询</button></div><div class="v12-toolbar-right"><button class="v12-btn primary" id="new-platform-lead">${icon('plus')}新建客资</button></div></div>${table(['客户','服务地区','来源渠道','状态/去重','提交时间','操作'],rows,'暂无平台手工录入客资')}</section>`);
  document.querySelector('#platform-filter').onclick=()=>{state.platformStatus=document.querySelector('#platform-status').value;renderPlatformLeads();};
  document.querySelector('#new-platform-lead').onclick=()=>openLeadForm(null);
  document.querySelectorAll('[data-detail]').forEach(button=>button.onclick=()=>showPlatformDetail(button.dataset.detail));
  document.querySelectorAll('[data-edit]').forEach(button=>button.onclick=()=>openLeadForm(state.platformItems.find(item=>item.id===button.dataset.edit)));
  document.querySelectorAll('[data-submit]').forEach(button=>button.onclick=()=>submitPlatformLead(button.dataset.submit));
}

function detailMarkup(item){
  const fields={客户姓名:item.customer_name,联系电话:item.phone||item.phone_masked,服务地区:`${item.city||''} ${item.district||''}`,来源渠道:item.source_channel,客户咨询类别:item.category_code,客户需求:item.need_summary,预算下限:item.budget_min,预算上限:item.budget_max,客户授权:item.consent_confirmed?'已确认':'未确认',客资状态:labels[item.status]||item.status,资料初审:labels[item.review_status]||item.review_status,重复检查:labels[item.duplicate_status]||item.duplicate_status,待处理原因:item.pending_reason,平台说明:item.review_note,提交时间:fmt(item.submitted_at),更新时间:fmt(item.updated_at)};
  return `<dl class="v12-detail">${Object.entries(fields).map(([name,val])=>`<dt>${esc(name)}</dt><dd>${esc(val??'--')}</dd>`).join('')}</dl>`;
}
function showPlatformDetail(id){const item=state.platformItems.find(row=>row.id===id);if(item)openDrawer('平台客资详情',detailMarkup(item));}

async function ensureCities(){if(!state.cities.length)state.cities=await request('/master-data/regions?level=CITY');return state.cities;}
async function loadDistricts(cityCode){state.districts=cityCode?await request('/master-data/regions'+query({parent_code:cityCode,level:'DISTRICT'})):[];return state.districts;}

async function openLeadForm(item){
  await ensureCities();
  const city=state.cities.find(row=>row.name===item?.city)||state.cities.find(row=>row.code===item?.region_code)||null;
  await loadDistricts(city?.code||'');
  const district=state.districts.find(row=>row.name===item?.district)||state.districts.find(row=>row.code===item?.region_code)||null;
  const body=`<div class="v12-form-grid"><div class="v12-field"><label>客户姓名 *</label><input class="v12-input" id="lead-name" value="${esc(item?.customer_name==='未填写'?'':item?.customer_name||'')}"></div><div class="v12-field"><label>手机号 *</label><input class="v12-input" id="lead-phone" inputmode="tel" maxlength="32" value="${esc(item?.phone||'')}"></div><div class="v12-field"><label>城市 *</label><select class="v12-select" id="lead-city"><option value="">请选择城市</option>${state.cities.map(row=>`<option value="${row.code}" ${city?.code===row.code?'selected':''}>${esc(row.name)}</option>`).join('')}</select></div><div class="v12-field"><label>区县</label><select class="v12-select" id="lead-district"><option value="">全市范围</option>${state.districts.map(row=>`<option value="${row.code}" ${district?.code===row.code?'selected':''}>${esc(row.name)}</option>`).join('')}</select></div><div class="v12-field"><label>来源渠道</label><input class="v12-input" id="lead-source" value="${esc(item?.source_channel||'')}"></div><div class="v12-field"><label>客户咨询类别</label><input class="v12-input" id="lead-category" value="${esc(item?.category_code||'')}"></div><div class="v12-field"><label>预算下限（元）</label><input class="v12-input" id="lead-budget-min" type="number" min="0" value="${esc(item?.budget_min??'')}"></div><div class="v12-field"><label>预算上限（元）</label><input class="v12-input" id="lead-budget-max" type="number" min="0" value="${esc(item?.budget_max??'')}"></div><div class="v12-field full"><label>客户需求 *</label><textarea class="v12-textarea" id="lead-need">${esc(item?.need_summary||'')}</textarea></div><div class="v12-field full"><label class="v12-check"><input id="lead-consent" type="checkbox" ${item?.consent_confirmed?'checked':''}><span><b>已获得客户信息授权 *</b><div class="v12-help">只有确认客户授权后才能提交。平台会安全保存联系方式，并自动检查是否已有相同客户。</div></span></label></div></div>`;
  openModal(item?'编辑客资草稿':'新建平台客资',body,`<button data-close class="v12-btn">取消</button><button id="save-lead" class="v12-btn primary">保存草稿</button>`);
  document.querySelector('#lead-city').onchange=async event=>{await loadDistricts(event.target.value);const select=document.querySelector('#lead-district');zsSetSafeHtml(select, '<option value="">全市范围</option>'+state.districts.map(row=>`<option value="${row.code}">${esc(row.name)}</option>`).join(''));};
  document.querySelector('#save-lead').onclick=()=>saveLeadForm(item);
}

function optionalNumber(selector){const raw=value(selector);return raw===''?null:Number(raw);}
async function saveLeadForm(item){
  const cityCode=value('#lead-city');const districtCode=value('#lead-district');
  const city=state.cities.find(row=>row.code===cityCode);const district=state.districts.find(row=>row.code===districtCode);
  const payload={customer_name:value('#lead-name'),phone:value('#lead-phone'),city:city?.name||'',district:district?.name||'',region_code:districtCode||cityCode,source_channel:value('#lead-source'),category_code:value('#lead-category'),need_summary:value('#lead-need'),budget_min:optionalNumber('#lead-budget-min'),budget_max:optionalNumber('#lead-budget-max'),consent_confirmed:Boolean(document.querySelector('#lead-consent')?.checked)};
  try{
    if(item)await request(`/v1.2/platform/leads/${item.id}`,{method:'PATCH',body:JSON.stringify(payload)});
    else await request('/v1.2/platform/leads',{method:'POST',body:JSON.stringify(payload)});
    closeOverlay();toast('客资草稿已保存');await renderPlatformLeads();
  }catch(error){toast(error.message,'error');}
}

async function submitPlatformLead(id){
  const item=state.platformItems.find(row=>row.id===id);if(!item)return;
  openModal('提交客资',`<p>系统会自动检查信息是否完整、已获得客户授权，以及是否存在重复记录。</p><div class="v12-note">检查通过后会进入待派发列表；疑似重复的客资会交由人工复核。</div>`,`<button data-close class="v12-btn">取消</button><button id="confirm-submit" class="v12-btn primary">确认提交</button>`);
  document.querySelector('#confirm-submit').onclick=async()=>{try{const result=await request(`/v1.2/platform/leads/${id}/submit`,{method:'POST'});closeOverlay();toast(result.dedup?.decision==='CLEAR'?'提交成功，已进入待人工派发池':'提交完成，请处理去重结论');await renderPlatformLeads();}catch(error){toast(error.message,'error');}};
}

function supplierActions(item){
  const actions=[`<button class="v12-btn small" data-supplier-detail="${item.id}">详情</button>`];
  if(item.status==='DUPLICATE'){
    if(can('lead.dedup.override'))actions.push(`<button class="v12-btn small primary" data-dedup-override="${item.id}">去重放行</button>`);
    actions.push(`<button class="v12-btn small danger" data-review-reject="${item.id}">驳回</button>`);
  }else if(item.review_status==='PENDING'&&item.status==='PENDING_REVIEW'){
    actions.push(`<button class="v12-btn small primary" data-review-approve="${item.id}">通过</button>`);
    actions.push(`<button class="v12-btn small danger" data-review-reject="${item.id}">驳回</button>`);
  }
  return actions.join('');
}

async function renderSupplierQueue(){
  const data=await request('/v1.2/admin/supplier-leads'+query({page:1,page_size:200,review_status:state.supplierReviewStatus}));
  state.supplierItems=data.items||[];
  const rows=state.supplierItems.map(item=>`<tr><td class="v12-customer"><strong>${esc(item.customer_name)}</strong><span>${icon('phone')}${esc(item.phone_masked||'--')}</span></td><td>${esc(item.city||'--')} ${esc(item.district||'')}</td><td>${esc(item.supplier_company_id||'--')}</td><td>${badge(item.review_status)}<div style="margin-top:6px">${badge(item.duplicate_status)}</div></td><td>${fmt(item.submitted_at||item.created_at)}</td><td><div class="v12-actions">${supplierActions(item)}</div></td></tr>`);
  zsSetSafeHtml(document.querySelector('#workspace'), `<section class="v12-panel"><div class="v12-toolbar"><div class="v12-toolbar-left"><h2>供应商资料初审</h2><select class="v12-select" id="supplier-review-status"><option value="PENDING" ${state.supplierReviewStatus==='PENDING'?'selected':''}>待审核</option><option value="APPROVED" ${state.supplierReviewStatus==='APPROVED'?'selected':''}>已通过</option><option value="REJECTED" ${state.supplierReviewStatus==='REJECTED'?'selected':''}>已驳回</option><option value="" ${state.supplierReviewStatus===''?'selected':''}>全部</option></select><button class="v12-btn" id="supplier-filter">查询</button></div><div class="v12-toolbar-right"><span class="v12-help">资料初审仅核对字段、来源、授权和重复结论</span></div></div>${table(['客户','服务地区','供应商公司','初审/去重','提交时间','操作'],rows,'暂无供应商客资')}</section>`);
  document.querySelector('#supplier-filter').onclick=()=>{state.supplierReviewStatus=document.querySelector('#supplier-review-status').value;renderSupplierQueue();};
  document.querySelectorAll('[data-supplier-detail]').forEach(button=>button.onclick=()=>showSupplierDetail(button.dataset.supplierDetail));
  document.querySelectorAll('[data-review-approve]').forEach(button=>button.onclick=()=>openSupplierReview(button.dataset.reviewApprove,true));
  document.querySelectorAll('[data-review-reject]').forEach(button=>button.onclick=()=>openSupplierReview(button.dataset.reviewReject,false));
  document.querySelectorAll('[data-dedup-override]').forEach(button=>button.onclick=()=>openDedupOverride(button.dataset.dedupOverride));
}

async function showSupplierDetail(id){try{const item=await request(`/v1.2/admin/supplier-leads/${id}`);openDrawer('供应商客资详情',detailMarkup(item));}catch(error){toast(error.message,'error');}}

function openDedupOverride(id){
  const item=state.supplierItems.find(row=>row.id===id);if(!item)return;
  openModal('去重人工放行',`${detailMarkup(item)}<div class="v12-note" style="margin-top:16px">放行后客资将返回“待资料初审”，仍需再次执行资料初审。请仅在确认属于独立有效需求时使用。</div><div class="v12-field" style="margin-top:16px"><label>放行原因 *</label><textarea class="v12-textarea" id="dedup-reason" placeholder="至少 5 个字符，说明为何不是同一重复需求"></textarea></div>`,`<button data-close class="v12-btn">取消</button><button id="confirm-dedup-override" class="v12-btn primary">确认放行</button>`);
  document.querySelector('#confirm-dedup-override').onclick=async()=>{const reason=value('#dedup-reason');if(reason.length<5){toast('放行原因至少 5 个字符','error');return;}try{await request(`/v1.2/admin/leads/${id}/dedup-override`,{method:'POST',body:JSON.stringify({event_id:null,reason})});closeOverlay();toast('已放行，客资返回待资料初审');state.supplierReviewStatus='PENDING';await renderSupplierQueue();}catch(error){toast(error.message,'error');}};
}

function openSupplierReview(id,approve){
  const item=state.supplierItems.find(row=>row.id===id);if(!item)return;
  openModal(approve?'通过供应商客资':'驳回供应商客资',`${detailMarkup(item)}<div class="v12-field" style="margin-top:16px"><label>${approve?'审核说明':'驳回原因 *'}</label><textarea class="v12-textarea" id="review-note" placeholder="${approve?'可填写资料核验说明':'请明确告知供应商需要修正的内容'}"></textarea></div>`,`<button data-close class="v12-btn">取消</button><button id="confirm-review" class="v12-btn ${approve?'primary':'danger'}">确认${approve?'通过':'驳回'}</button>`);
  document.querySelector('#confirm-review').onclick=async()=>{const note=value('#review-note');if(!approve&&!note){toast('驳回时必须填写原因','error');return;}try{await request(`/v1.2/admin/supplier-leads/${id}/review`,{method:'POST',body:JSON.stringify({decision:approve?'APPROVE':'REJECT',note})});closeOverlay();toast('资料初审已完成');await renderSupplierQueue();}catch(error){toast(error.message,'error');}};
}

boot();
