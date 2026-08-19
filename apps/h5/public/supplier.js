const API='/api/v1';
const app=document.querySelector('#app');
const toastEl=document.querySelector('#toast');
const overlay=document.querySelector('#overlay');
const state={
  me:null,
  tab:'list',
  capabilities:[],
  items:[],
  cities:[],
  districts:[],
  editing:null,
  listPage:1,
  listPageSize:20,
  listStatus:'',
  listTotal:0
};
const esc=(value='')=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const fmt=value=>value?new Date(value).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'--';
const labels={DRAFT:'草稿',PENDING_REVIEW:'待平台初审',READY_DISPATCH:'待人工派发',DUPLICATE:'重复/疑似重复',INVALID:'资料已驳回',CLOSED:'已关闭',PENDING:'待审核',APPROVED:'已通过',REJECTED:'已驳回',CLEAR:'无重复',HARD_DUPLICATE:'90天硬重复',REWARD_DUPLICATE:'奖励重复',HISTORICAL_SUSPECT:'历史疑似',OVERRIDDEN:'已人工放行'};
const statusClass=value=>({READY_DISPATCH:'ok',APPROVED:'ok',CLEAR:'ok',OVERRIDDEN:'blue',DRAFT:'',PENDING_REVIEW:'warn',PENDING:'warn',DUPLICATE:'warn',REWARD_DUPLICATE:'warn',HISTORICAL_SUSPECT:'warn',HARD_DUPLICATE:'bad',INVALID:'bad',REJECTED:'bad'}[value]||'');
const badge=value=>`<span class="supplier-status ${statusClass(value)}">${esc(labels[value]||value||'--')}</span>`;
const value=id=>document.querySelector(id)?.value?.trim()||'';

async function api(path,options={}){
  const headers={...(options.headers||{})};
  if(options.body!==undefined&&!(options.body instanceof FormData))headers['Content-Type']='application/json';
  const response=await fetch(API+path,{...options,headers,credentials:'include'});
  let payload={};try{payload=await response.json();}catch{payload={message:response.statusText};}
  if(!response.ok||payload.code!=='OK'){const error=new Error(payload.message||'请求失败');error.code=payload.code;error.details=payload.details;throw error;}
  return payload.data;
}
function toast(message,type=''){toastEl.textContent=message;toastEl.className=`toast show ${type==='error'?'error':''}`;setTimeout(()=>toastEl.className='toast',2600);}
function capability(){return state.capabilities.find(item=>item.capability_code==='LEAD_SUPPLIER');}
function capabilityApproved(){const item=capability();return Boolean(item?.active&&item?.review_status==='APPROVED');}
function capabilityBlock(){
  const item=capability();
  if(capabilityApproved())return `<div><b>供应商能力已开通</b><div style="font-size:12px;opacity:.8;margin-top:3px">可上传客资并查看资料初审状态</div></div>${badge('APPROVED')}`;
  if(item?.review_status==='PENDING')return `<div><b>供应商能力审核中</b><div style="font-size:12px;opacity:.8;margin-top:3px">平台审核通过后可上传客资</div></div>${badge('PENDING')}`;
  return `<div><b>尚未开通供应商能力</b><div style="font-size:12px;opacity:.8;margin-top:3px">提交申请后由平台审核</div></div><button class="supplier-btn gold small" id="request-capability">申请开通</button>`;
}
function header(){return `<header class="supplier-header"><div class="supplier-brand"><img src="./logo.png" alt="合家美宅"><div><strong>合家美宅供应商客资</strong><small>上传 · 初审</small></div></div><button class="supplier-back" id="back-h5">返回客资助手</button></header>`;}
function shell(content){zsSetSafeHtml(app, `${header()}<main class="supplier-main"><section class="supplier-hero"><h1>优质客资供给</h1><p>上传前请确认客户授权。资料通过平台初审后进入待人工派发池，其他公司领取后按规则进入 3 个工作日奖励观察期。</p><div class="supplier-capability">${capabilityBlock()}</div></section><nav class="supplier-tabs"><button class="supplier-tab ${state.tab==='list'?'active':''}" data-tab="list">我的客资</button><button class="supplier-tab ${state.tab==='upload'?'active':''}" data-tab="upload" ${capabilityApproved()?'':'disabled'}>上传客资</button></nav>${content}</main>`);bindCommon();}
function bindCommon(){
  document.querySelector('#back-h5').onclick=()=>{location.href='./#/profile';};
  document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>{if(button.disabled)return;state.tab=button.dataset.tab;state.editing=null;render();});
  const requestButton=document.querySelector('#request-capability');if(requestButton)requestButton.onclick=requestSupplierCapability;
}
function loading(){shell('<div class="supplier-card supplier-loading">正在加载…</div>');}
function empty(text){return `<div class="supplier-empty"><b>⌕</b>${esc(text)}</div>`;}
function closeSheet(){overlay.innerHTML='';}
function openSheet(title,body){zsSetSafeHtml(overlay, `<div class="supplier-overlay"><section class="supplier-sheet"><div class="supplier-sheet-head"><h2>${esc(title)}</h2><button class="supplier-btn small" id="close-sheet">关闭</button></div>${body}</section></div>`);document.querySelector('#close-sheet').onclick=closeSheet;}

async function boot(){
  try{
    state.me=await api('/auth/me');
    if(!state.me.permissions?.includes('*')&&!state.me.permissions?.includes('supplier.lead.manage'))throw new Error('当前账号没有供应商客资权限');
    state.capabilities=await api('/v1.2/company/capabilities');
    await render();
  }catch(error){
    if(error.code==='AUTH_REQUIRED'||error.code==='AUTH_INVALID'){location.href='./#/login';return;}
    zsSetSafeHtml(app, `${header()}<main class="supplier-main"><div class="supplier-error">${esc(error.message||'页面加载失败')}</div></main>`);
    document.querySelector('#back-h5').onclick=()=>{location.href='./#/profile';};
  }
}
async function render(){loading();try{if(state.tab==='upload')await renderUpload(state.editing);else await renderList();}catch(error){toast(error.message,'error');shell(`<div class="supplier-error">${esc(error.message||'加载失败')}</div>`);}}

async function requestSupplierCapability(){
  try{await api('/v1.2/company/capabilities',{method:'POST',body:JSON.stringify({capability_code:'LEAD_SUPPLIER'})});state.capabilities=await api('/v1.2/company/capabilities');toast('供应商能力申请已提交');await render();}catch(error){toast(error.message,'error');}
}

async function renderList(){
  const data=await api('/v1.2/supplier/leads'+queryString({page:state.listPage,page_size:state.listPageSize,status:state.listStatus}));
  state.items=data.items||[];
  state.listTotal=data.total||0;
  const totalPages=Math.max(1,Math.ceil(state.listTotal/state.listPageSize));
  if(state.listPage>totalPages){state.listPage=totalPages;return renderList();}
  const rows=state.items.map(item=>`<article class="supplier-lead"><div class="supplier-lead-top"><div><h3>${esc(item.customer_name)}</h3><p>${esc(item.phone_masked||'--')} · ${esc(item.city||'--')} ${esc(item.district||'')}</p></div>${badge(item.status)}</div><p>资料初审：${labels[item.review_status]||item.review_status||'--'}　去重：${labels[item.duplicate_status]||item.duplicate_status||'--'}<br>提交时间：${fmt(item.submitted_at||item.created_at)}</p>${item.review_note?`<div class="supplier-notice">平台说明：${esc(item.review_note)}</div>`:''}<div class="supplier-lead-actions"><button class="supplier-btn small" data-detail="${item.id}">查看详情</button>${item.status==='DRAFT'?`<button class="supplier-btn small primary" data-edit="${item.id}">继续编辑</button><button class="supplier-btn small gold" data-submit="${item.id}">提交初审</button>`:''}</div></article>`);
  const pager=state.listTotal?`<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:14px"><button class="supplier-btn small" id="previous-page" ${state.listPage<=1?'disabled':''}>上一页</button><span class="supplier-muted">第 ${state.listPage} / ${totalPages} 页，共 ${state.listTotal} 条</span><button class="supplier-btn small" id="next-page" ${state.listPage>=totalPages?'disabled':''}>下一页</button></div>`:'';
  shell(`<section class="supplier-card"><div class="supplier-card-head"><div><h2>我的客资</h2><div class="supplier-muted">仅显示当前公司上传的客资，共 ${state.listTotal} 条</div></div><select class="supplier-select" id="supplier-status" style="width:auto"><option value="" ${state.listStatus===''?'selected':''}>全部</option>${['DRAFT','PENDING_REVIEW','READY_DISPATCH','DUPLICATE','INVALID'].map(option=>`<option value="${option}" ${state.listStatus===option?'selected':''}>${esc(labels[option])}</option>`).join('')}</select></div><div class="supplier-list">${rows.length?rows.join(''):empty('还没有上传客资')}</div>${pager}</section>`);
  document.querySelector('#supplier-status').onchange=event=>{state.listStatus=event.target.value;state.listPage=1;renderList();};
  const previous=document.querySelector('#previous-page');if(previous)previous.onclick=()=>{if(state.listPage>1){state.listPage-=1;renderList();}};
  const next=document.querySelector('#next-page');if(next)next.onclick=()=>{if(state.listPage<totalPages){state.listPage+=1;renderList();}};
  document.querySelectorAll('[data-detail]').forEach(button=>button.onclick=()=>showDetail(button.dataset.detail));
  document.querySelectorAll('[data-edit]').forEach(button=>button.onclick=()=>editLead(button.dataset.edit));
  document.querySelectorAll('[data-submit]').forEach(button=>button.onclick=()=>submitLead(button.dataset.submit));
}
function queryString(values){const params=new URLSearchParams();Object.entries(values).forEach(([key,val])=>{if(val!==undefined&&val!==null&&val!=='')params.set(key,val);});const result=params.toString();return result?`?${result}`:'';}

async function ensureCities(){if(!state.cities.length)state.cities=await api('/master-data/regions?level=CITY');return state.cities;}
async function loadDistricts(cityCode){state.districts=cityCode?await api('/master-data/regions'+queryString({parent_code:cityCode,level:'DISTRICT'})):[];return state.districts;}
async function editLead(id){try{state.editing=await api(`/v1.2/supplier/leads/${id}`);state.tab='upload';await renderUpload(state.editing);}catch(error){toast(error.message,'error');}}

async function renderUpload(item=null){
  if(!capabilityApproved()){state.tab='list';await renderList();return;}
  await ensureCities();const city=state.cities.find(row=>row.name===item?.city)||state.cities.find(row=>row.code===item?.region_code)||null;await loadDistricts(city?.code||'');const district=state.districts.find(row=>row.name===item?.district)||state.districts.find(row=>row.code===item?.region_code)||null;
  shell(`<section class="supplier-card"><div class="supplier-card-head"><div><h2>${item?'编辑客资草稿':'上传新客资'}</h2><div class="supplier-muted">带 * 字段提交初审时必须完整</div></div>${item?badge(item.status):''}</div><form class="supplier-form" id="lead-form"><div class="supplier-grid"><div class="supplier-field"><label>客户姓名 *</label><input class="supplier-input" id="lead-name" maxlength="64" value="${esc(item?.customer_name==='未填写'?'':item?.customer_name||'')}"></div><div class="supplier-field"><label>手机号 *</label><input class="supplier-input" id="lead-phone" inputmode="tel" maxlength="32" value="${esc(item?.phone||'')}"></div></div><div class="supplier-grid"><div class="supplier-field"><label>城市 *</label><select class="supplier-select" id="lead-city"><option value="">请选择</option>${state.cities.map(row=>`<option value="${row.code}" ${city?.code===row.code?'selected':''}>${esc(row.name)}</option>`).join('')}</select></div><div class="supplier-field"><label>区县</label><select class="supplier-select" id="lead-district"><option value="">全市范围</option>${state.districts.map(row=>`<option value="${row.code}" ${district?.code===row.code?'selected':''}>${esc(row.name)}</option>`).join('')}</select></div></div><div class="supplier-grid"><div class="supplier-field"><label>来源渠道</label><input class="supplier-input" id="lead-source" value="${esc(item?.source_channel||'供应商推荐')}"></div><div class="supplier-field"><label>业务类目</label><input class="supplier-input" id="lead-category" value="${esc(item?.category_code||'')}"></div></div><div class="supplier-grid"><div class="supplier-field"><label>预算下限（元）</label><input class="supplier-input" id="lead-budget-min" type="number" min="0" value="${esc(item?.budget_min??'')}"></div><div class="supplier-field"><label>预算上限（元）</label><input class="supplier-input" id="lead-budget-max" type="number" min="0" value="${esc(item?.budget_max??'')}"></div></div><div class="supplier-field"><label>客户需求 *</label><textarea class="supplier-textarea" id="lead-need" maxlength="2000">${esc(item?.need_summary||'')}</textarea></div><label class="supplier-check"><input type="checkbox" id="lead-consent" ${item?.consent_confirmed?'checked':''}><span><b>已获得客户授权 *</b><br>我确认客户知晓其联系方式和建房/装修需求将提交给合家美宅平台，用于业务对接。</span></label><div class="supplier-notice">手机号将加密存储并以不可逆 HMAC 指纹进行 90/180/365 天去重。资料初审不会进行前置电话核验。</div><div class="supplier-actions"><button type="button" class="supplier-btn" id="save-draft">保存草稿</button><button type="button" class="supplier-btn primary" id="save-submit">保存并提交初审</button></div></form></section>`);
  document.querySelector('#lead-city').onchange=async event=>{await loadDistricts(event.target.value);zsSetSafeHtml(document.querySelector('#lead-district'), '<option value="">全市范围</option>'+state.districts.map(row=>`<option value="${row.code}">${esc(row.name)}</option>`).join(''));};
  document.querySelector('#save-draft').onclick=()=>saveForm(item,false);
  document.querySelector('#save-submit').onclick=()=>saveForm(item,true);
}
function optionalNumber(selector){const raw=value(selector);return raw===''?null:Number(raw);}
function formPayload(){const cityCode=value('#lead-city');const districtCode=value('#lead-district');const city=state.cities.find(row=>row.code===cityCode);const district=state.districts.find(row=>row.code===districtCode);return {customer_name:value('#lead-name'),phone:value('#lead-phone'),city:city?.name||'',district:district?.name||'',region_code:districtCode||cityCode,source_channel:value('#lead-source'),category_code:value('#lead-category'),need_summary:value('#lead-need'),budget_min:optionalNumber('#lead-budget-min'),budget_max:optionalNumber('#lead-budget-max'),consent_confirmed:Boolean(document.querySelector('#lead-consent')?.checked)};}
async function saveForm(item,submitAfter){
  try{
    let saved;if(item)saved=await api(`/v1.2/supplier/leads/${item.id}`,{method:'PATCH',body:JSON.stringify(formPayload())});else saved=await api('/v1.2/supplier/leads',{method:'POST',body:JSON.stringify(formPayload())});
    if(submitAfter){const result=await api(`/v1.2/supplier/leads/${saved.id}/submit`,{method:'POST'});toast(result.dedup?.decision==='CLEAR'?'已提交平台初审':'已提交，请等待重复结论复核');}
    else toast('草稿已保存');
    state.editing=null;state.tab='list';state.listPage=1;await renderList();
  }catch(error){toast(error.message,'error');}
}
async function submitLead(id){
  openSheet('提交平台初审',`<p class="supplier-muted">提交后将校验字段、客户授权和手机号重复情况。通过资料初审后进入待人工派发池。</p><div class="supplier-notice">正常客资不会进行前置电话核验。</div><button class="supplier-btn primary block" id="confirm-submit" style="margin-top:14px">确认提交</button>`);
  document.querySelector('#confirm-submit').onclick=async()=>{try{await api(`/v1.2/supplier/leads/${id}/submit`,{method:'POST'});closeSheet();toast('客资已提交平台初审');state.listPage=1;await renderList();}catch(error){toast(error.message,'error');}};
}
async function showDetail(id){
  try{const item=await api(`/v1.2/supplier/leads/${id}`);const fields={客户姓名:item.customer_name,联系电话:item.phone||item.phone_masked,服务地区:`${item.city||''} ${item.district||''}`,来源渠道:item.source_channel,业务类目:item.category_code,客户需求:item.need_summary,授权确认:item.consent_confirmed?'已确认':'未确认',客资状态:labels[item.status]||item.status,资料初审:labels[item.review_status]||item.review_status,去重结论:labels[item.duplicate_status]||item.duplicate_status,平台说明:item.review_note,提交时间:fmt(item.submitted_at),更新时间:fmt(item.updated_at)};openSheet('客资详情',`<dl class="supplier-detail">${Object.entries(fields).map(([name,val])=>`<dt>${esc(name)}</dt><dd>${esc(val??'--')}</dd>`).join('')}</dl>${item.status==='DRAFT'?`<button class="supplier-btn primary block" id="detail-edit" style="margin-top:14px">继续编辑</button>`:''}`);const edit=document.querySelector('#detail-edit');if(edit)edit.onclick=()=>{closeSheet();editLead(item.id);};}catch(error){toast(error.message,'error');}
}

boot();
