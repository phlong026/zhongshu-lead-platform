const API='/api/v1',app=document.querySelector('#app'),toastEl=document.querySelector('#toast'),modalRoot=document.querySelector('#modal-root');
const S={me:null,view:'overview',id:'',page:1,companyStatus:'PENDING',companyCapabilityPage:1,companyAreaPage:1};
const P={overview:['经营总览','layout-dashboard',['report.v12.read']],review:['供应商初审','user-check',['lead.supplier.review']],dispatch:['人工派发','hand-claim',['lead.dispatch']],companies:['加盟商审核','building',['company.profile.review']],returns:['退回与核验','rotate-ccw',['return.read','return.review','verification.read']],rewards:['奖励管理','award',['reward.read','reward.manage']],audit:['报表与审计','search',['audit.read']]};
const SYSTEM_LINKS=[
  {key:'users',label:'账号与角色',icon:'users',href:'./index.html#/users',permissions:['*']},
  {key:'companies',label:'加盟商公司',icon:'building',href:'./index.html#/companies',permissions:['company.read']},
  {key:'points',label:'积分档位与定价',icon:'coins',href:'./index.html#/points',permissions:['points.read','points.package.manage']},
  {key:'recharge',label:'人工充值',icon:'plus',href:'./index.html#/recharge',permissions:['points.recharge']},
  {key:'ledgers',label:'积分流水',icon:'receipt',href:'./index.html#/ledgers',permissions:['points.read']},
  {key:'calendar',label:'工作日历',icon:'calendar',href:'./index.html#/calendar',permissions:['calendar.read']},
  {key:'configs',label:'规则配置',icon:'settings',href:'./index.html#/configs',permissions:['*']},
];
const L={PENDING:'待审核',PENDING_REVIEW:'待初审',READY_DISPATCH:'待派发',PENDING_CLAIM:'待领取',CLAIMED:'已领取',SUBMITTED:'已提交',VERIFYING:'核验中',REVIEWING:'待终审',NEED_MORE_EVIDENCE:'待补证',APPROVED:'已通过',REJECTED:'已驳回',OBSERVING:'观察期',FROZEN:'已冻结',SETTLED:'已结算',CANCELLED:'已取消',REVERSED:'已冲正'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>v?new Date(v).toLocaleString('zh-CN'):'--',can=p=>(S.me?.permissions||[]).some(x=>x==='*'||x===p),label=v=>L[v]||v||'--';
const icon=name=>window.ZSIconSystem?.svg?.(name)||'';
const badge=v=>`<span class="ops-status ${['APPROVED','SETTLED','CLAIMED'].includes(v)?'ok':['REJECTED','CANCELLED','REVERSED'].includes(v)?'bad':'warn'}">${esc(label(v))}</span>`;
const qs=o=>{const p=new URLSearchParams;Object.entries(o).forEach(([k,v])=>v!==''&&v!=null&&p.set(k,v));return p.toString()?`?${p}`:''};
async function api(path,opt={}){const h={...(opt.headers||{})};if(opt.body&&!(opt.body instanceof FormData))h['Content-Type']='application/json';const r=await fetch(API+path,{...opt,headers:h,credentials:'include'});let j={};try{j=await r.json()}catch{}if(!r.ok||j.code!=='OK')throw new Error(j.message||'请求失败');return j.data}
function toast(m,e=false){toastEl.textContent=m;toastEl.className=`ops-toast show ${e?'error':''}`;clearTimeout(toast.t);toast.t=setTimeout(()=>toastEl.className='ops-toast',2400)}
function closeModal(){modalRoot.innerHTML=''}
function modal(title,body,bind){zsSetSafeHtml(modalRoot, `<div class="ops-overlay"><section class="ops-modal"><div class="ops-modal-head"><h2>${esc(title)}</h2><button class="ops-btn" id="modal-close">关闭</button></div>${body}</section></div>`);document.querySelector('#modal-close').onclick=closeModal;bind?.()}
function allowed(meta){return meta[2].some(can)}
function nav(){return Object.entries(P).filter(([,m])=>allowed(m)).map(([k,m])=>`<button class="${S.view===k?'active':''}" data-view="${k}"><span>${icon(m[1])}</span><span>${m[0]}</span></button>`).join('')}
function visibleSystemLinks(){return SYSTEM_LINKS.filter(link=>link.permissions.some(can))}
function systemNav(links){return links.map(link=>`<a data-system-setting="${link.key}" href="${link.href}" title="进入现有安全设置页面"><span>${icon(link.icon)}</span><span>${link.label}</span></a>`).join('')}
function shell(body){
  const meta=P[S.view]||P.overview;
  const systemLinks=visibleSystemLinks();
  const systemShortcut=systemLinks[0];
  const systemSection=systemLinks.length?`<div class="ops-menu-label">系统设置</div><nav class="ops-menu ops-system-menu">${systemNav(systemLinks)}</nav><p class="ops-boundary">设置页沿用现有安全模块；旧业务写接口保持关闭，配置值与场景参数本轮不调整。</p>`:'';
  const shortcut=systemShortcut?`<a class="ops-btn" data-system-settings-shortcut href="${systemShortcut.href}">${icon('settings')}系统设置</a>`:'';
  zsSetSafeHtml(app, `<div class="ops-shell"><aside class="ops-side"><div class="ops-brand"><img class="ops-logo" src="./logo.png" alt="合家美宅"><div><strong>合家美宅</strong><small>客资运营台</small></div></div><div class="ops-menu-label">业务运营</div><nav class="ops-menu">${nav()}</nav>${systemSection}<div class="ops-side-foot">${esc(S.me?.display_name||'')}</div></aside><section class="ops-main"><header class="ops-top"><div class="ops-title"><h1>${meta[0]}</h1><p>客资运营管理</p></div><div class="ops-top-actions">${shortcut}<button class="ops-btn primary" id="refresh">${icon('rotate-ccw')}刷新</button></div></header><main class="ops-content">${body}</main></section></div>`);
  document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>go(button.dataset.view));
  document.querySelector('#refresh').onclick=render;
}
function firstAllowedView(){return Object.keys(P).find(view=>allowed(P[view]))||''}
function syncRouteFromUrl({canonicalize=false}={}){
  const url=new URL(location.href);
  const requestedView=url.searchParams.get('view')||'overview';
  const nextView=P[requestedView]&&allowed(P[requestedView])?requestedView:firstAllowedView();
  if(!nextView)return false;
  S.view=nextView;
  S.id=url.searchParams.get('id')||'';
  S.page=1;
  if(canonicalize&&requestedView!==nextView){
    url.searchParams.set('view',nextView);
    url.searchParams.delete('id');
    history.replaceState(null,'',url);
  }
  return true;
}
function go(view,id=''){
  if(!P[view]||!allowed(P[view])||(S.view===view&&S.id===id))return;
  const url=new URL(location.href);
  url.searchParams.set('view',view);
  id?url.searchParams.set('id',id):url.searchParams.delete('id');
  history.pushState(null,'',url);
  syncRouteFromUrl();
  render();
}
function table(head,rows){return `<div class="ops-table-wrap"><table class="ops-table"><thead><tr>${head.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.join('')||`<tr><td colspan="${head.length}" class="ops-empty">暂无数据</td></tr>`}</tbody></table></div>`}
function pager(d){const pages=Math.max(1,Math.ceil((d.total||0)/(d.page_size||20)));return `<div class="ops-pager"><button class="ops-btn" id="prev" ${S.page<=1?'disabled':''}>上一页</button><span>${S.page}/${pages}，共 ${d.total||0} 条</span><button class="ops-btn" id="next" ${S.page>=pages?'disabled':''}>下一页</button></div>`}
function bindPager(d,fn){const pages=Math.max(1,Math.ceil((d.total||0)/(d.page_size||20)));document.querySelector('#prev')?.addEventListener('click',()=>{S.page--;fn()});document.querySelector('#next')?.addEventListener('click',()=>{S.page=Math.min(pages,S.page+1);fn()})}
async function render(){shell('<div class="ops-loading">加载中…</div>');try{await ({overview,review,dispatch,companies,returns,rewards,audit}[S.view]||overview)()}catch(e){shell(`<div class="ops-error">${esc(e.message)}</div>`);toast(e.message,true)}}
async function overview(){const d=await api('/v1.2/reports/overview');const k=[['客资总量',d.leads.total,'list'],['派发单',d.assignments.total,'hand-claim'],['退回申诉',d.returns.total,'rotate-ccw'],['供应奖励',d.supplier_rewards.points+' 分','award'],['积分流水',d.points_ledger.count,'coins'],['净积分变化',d.points_ledger.net_delta,'activity']];shell(`<div class="ops-grid">${k.map(x=>`<div class="ops-kpi"><i>${icon(x[2])}</i><small>${x[0]}</small><b>${x[1]}</b></div>`).join('')}</div><section class="ops-card"><h2>状态分布</h2><pre class="ops-code">${esc(JSON.stringify({leads:d.leads.by_status,assignments:d.assignments.by_status,returns:d.returns.by_status,rewards:d.supplier_rewards.by_status},null,2))}</pre></section>`)}
async function review(){const d=await api(`/v1.2/admin/supplier-leads${qs({page:S.page,page_size:20})}`);const rows=(d.items||[]).map(x=>`<tr><td><b>${esc(x.customer_name)}</b><br>${esc(x.phone_masked||'--')}</td><td>${esc(x.city||'--')} ${esc(x.district||'')}</td><td>${badge(x.status)} ${badge(x.review_status)}</td><td>${esc(label(x.duplicate_status))}</td><td>${fmt(x.submitted_at)}</td><td><button class="ops-btn" data-detail="${x.id}">详情</button>${x.review_status==='PENDING'?` <button class="ops-btn primary" data-review="${x.id}:APPROVE">通过</button> <button class="ops-btn danger" data-review="${x.id}:REJECT">驳回</button>`:''}</td></tr>`);shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>供应商客资初审</h2><p>列表只展示脱敏手机号。</p></div></div>${table(['客户','区域','状态','去重','提交时间','操作'],rows)}${pager(d)}</section>`);bindPager(d,review);document.querySelectorAll('[data-detail]').forEach(b=>b.onclick=()=>reviewDetail(b.dataset.detail));document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>{const [id,decision]=b.dataset.review.split(':');reviewAction(id,decision)});if(S.id){const id=S.id;S.id='';reviewDetail(id)}}
async function reviewDetail(id){const x=await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(id)}`);modal('客资初审详情',`<div class="ops-detail-grid">${[['业务ID',x.id],['客户',x.customer_name],['手机号',x.phone_masked],['状态',label(x.status)],['初审',label(x.review_status)],['去重',label(x.duplicate_status)],['区域',`${x.city||''} ${x.district||''}`],['供应商',x.supplier_company_id]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>客户需求</h3><p class="ops-muted">${esc(x.need_summary||'--')}</p></section><button class="ops-btn" id="trace">业务追踪</button>`,()=>document.querySelector('#trace').onclick=()=>{closeModal();go('audit',id)})}
async function reviewAction(id,decision){const note=prompt(decision==='REJECT'?'请输入驳回说明（必填）':'请输入审核说明（可选）','')??'';if(decision==='REJECT'&&!note.trim())return toast('驳回说明不能为空',true);try{await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(id)}/review`,{method:'POST',body:JSON.stringify({decision,note:note.trim()||null})});toast('初审结果已提交');review()}catch(e){toast(e.message,true)}}
const CAPABILITY_LABEL={LEAD_SUPPLIER:'客资供应能力',LEAD_RECEIVER:'客资接收能力'};
const cleanProfileNote=note=>String(note||'').replace(/^\[REMOVE_REQUEST\]\s*/,'');
function capabilityReviewActions(item){
  if(item.review_status==='PENDING')return `<button class="ops-btn primary" data-cap-company="${esc(item.company_id)}" data-cap-code="${esc(item.capability_code)}" data-cap-decision="APPROVE">通过</button> <button class="ops-btn danger" data-cap-company="${esc(item.company_id)}" data-cap-code="${esc(item.capability_code)}" data-cap-decision="REJECT">驳回</button>`;
  if(item.review_status==='APPROVED'&&item.active)return `<button class="ops-btn danger" data-cap-company="${esc(item.company_id)}" data-cap-code="${esc(item.capability_code)}" data-cap-decision="REJECT">停用</button>`;
  return `<button class="ops-btn primary" data-cap-company="${esc(item.company_id)}" data-cap-code="${esc(item.capability_code)}" data-cap-decision="APPROVE">重新通过</button>`;
}
function areaReviewActions(item){
  if(item.review_status!=='PENDING')return '--';
  const removal=String(item.review_note||'').startsWith('[REMOVE_REQUEST]');
  return `<button class="ops-btn primary" data-area-id="${esc(item.id)}" data-area-decision="APPROVE">${removal?'同意移除':'通过'}</button> <button class="ops-btn danger" data-area-id="${esc(item.id)}" data-area-decision="REJECT">${removal?'驳回移除':'驳回'}</button>`;
}
function companyQueuePager(data,prefix,currentPage){
  const pages=Math.max(1,Math.ceil((data.total||0)/(data.page_size||20)));
  return `<div class="ops-pager"><button class="ops-btn" id="${prefix}-prev" ${currentPage<=1?'disabled':''}>上一页</button><span>${currentPage}/${pages}，共 ${data.total||0} 条</span><button class="ops-btn" id="${prefix}-next" ${currentPage>=pages?'disabled':''}>下一页</button></div>`;
}
function bindCompanyQueuePager(data,prefix,pageKey){
  const pages=Math.max(1,Math.ceil((data.total||0)/(data.page_size||20)));
  document.querySelector(`#${prefix}-prev`).onclick=()=>{S[pageKey]=Math.max(1,S[pageKey]-1);companies()};
  document.querySelector(`#${prefix}-next`).onclick=()=>{S[pageKey]=Math.min(pages,S[pageKey]+1);companies()};
}
async function companies(){
  const [capabilities,areas]=await Promise.all([
    api(`/v1.2/admin/company-capabilities${qs({review_status:S.companyStatus,page:S.companyCapabilityPage,page_size:20})}`),
    api(`/v1.2/admin/service-areas${qs({review_status:S.companyStatus,page:S.companyAreaPage,page_size:20})}`),
  ]);
  const capabilityRows=(capabilities.items||[]).map(item=>`<tr><td><b>${esc(item.company_name)}</b><br><small>${esc(item.company_code)}</small></td><td>${esc(CAPABILITY_LABEL[item.capability_code]||item.capability_code)}</td><td>${badge(item.review_status)}<br><small>${item.active?'已启用':'未启用'}</small></td><td>${esc(cleanProfileNote(item.review_note)||'--')}</td><td>${fmt(item.reviewed_at)}</td><td>${capabilityReviewActions(item)}</td></tr>`);
  const areaRows=(areas.items||[]).map(item=>{const removal=String(item.review_note||'').startsWith('[REMOVE_REQUEST]');return `<tr><td><b>${esc(item.company_name)}</b><br><small>${esc(item.company_code)}</small></td><td>${esc(item.region_code)}<br><small>${esc(item.is_primary_city?'主要城市':item.region_level)}</small></td><td>${badge(item.review_status)}<br><small>${removal&&item.active?'待移除，当前仍生效':item.active?'已生效':'未生效'}</small></td><td>${esc(cleanProfileNote(item.review_note)||'--')}</td><td>${fmt(item.reviewed_at)}</td><td>${areaReviewActions(item)}</td></tr>`});
  shell(`<section class="ops-card company-review"><div class="ops-card-head"><div><h2>加盟商能力与服务区域审核申请</h2><p>供应与接收能力独立审核；区域移除申请在批准前继续保持原服务资格。</p></div><select class="ops-input" id="company-review-status" style="width:auto"><option value="PENDING" ${S.companyStatus==='PENDING'?'selected':''}>待审核</option><option value="APPROVED" ${S.companyStatus==='APPROVED'?'selected':''}>已通过</option><option value="REJECTED" ${S.companyStatus==='REJECTED'?'selected':''}>已驳回</option></select></div><h3>公司能力（${capabilities.total||0}）</h3>${table(['加盟商','能力','状态','审核说明','审核时间','操作'],capabilityRows)}${companyQueuePager(capabilities,'capability',S.companyCapabilityPage)}</section><section class="ops-card company-review"><h3>服务区域（${areas.total||0}）</h3>${table(['加盟商','区域','状态','审核说明','审核时间','操作'],areaRows)}${companyQueuePager(areas,'area',S.companyAreaPage)}</section>`);
  document.querySelector('#company-review-status').onchange=event=>{S.companyStatus=event.target.value;S.companyCapabilityPage=1;S.companyAreaPage=1;companies()};
  bindCompanyQueuePager(capabilities,'capability','companyCapabilityPage');
  bindCompanyQueuePager(areas,'area','companyAreaPage');
  document.querySelectorAll('[data-cap-decision]').forEach(button=>button.onclick=()=>reviewCompanyCapability(button));
  document.querySelectorAll('[data-area-decision]').forEach(button=>button.onclick=()=>reviewCompanyArea(button));
}
async function reviewCompanyCapability(button){
  if(button.dataset.busy==='1')return;
  const decision=button.dataset.capDecision;
  const input=prompt(decision==='REJECT'?'请输入驳回或停用原因（必填）':'请输入审核说明（可选）','');
  if(input===null)return;
  const note=input.trim();
  if(decision==='REJECT'&&!note)return toast('驳回或停用原因不能为空',true);
  button.dataset.busy='1';button.disabled=true;
  try{await api(`/v1.2/admin/companies/${encodeURIComponent(button.dataset.capCompany)}/capabilities/${encodeURIComponent(button.dataset.capCode)}/review`,{method:'POST',body:JSON.stringify({decision,note:note||null})});toast('公司能力审核已完成');await companies()}catch(error){delete button.dataset.busy;button.disabled=false;toast(error.message,true)}
}
async function reviewCompanyArea(button){
  if(button.dataset.busy==='1')return;
  const decision=button.dataset.areaDecision;
  const input=prompt(decision==='REJECT'?'请输入驳回说明（必填）':'请输入审核说明（可选）','');
  if(input===null)return;
  if(decision==='REJECT'&&!input.trim())return toast('驳回说明不能为空',true);
  button.dataset.busy='1';button.disabled=true;
  try{await api(`/v1.2/admin/service-areas/${encodeURIComponent(button.dataset.areaId)}/review`,{method:'POST',body:JSON.stringify({decision,note:input.trim()||null})});toast('服务区域审核已完成');await companies()}catch(error){delete button.dataset.busy;button.disabled=false;toast(error.message,true)}
}
async function dispatch(){const d=await api(`/v1.2/dispatch-pool${qs({page:S.page,page_size:20})}`);const rows=(d.items||[]).map(x=>`<tr><td><b>${esc(x.customer_name)}</b><br>${esc(x.phone_masked||'--')}</td><td>${esc(x.city||'--')} ${esc(x.district||'')}</td><td>${esc(x.source_kind||'--')}</td><td>${esc(x.need_summary||'--')}</td><td><button class="ops-btn primary" data-candidate="${x.id}">选择接收公司</button></td></tr>`);shell(`<section class="ops-card"><h2>待人工派发池</h2>${table(['客户','区域','来源','需求','操作'],rows)}${pager(d)}</section>`);bindPager(d,dispatch);document.querySelectorAll('[data-candidate]').forEach(b=>b.onclick=()=>candidates(b.dataset.candidate));if(S.id){const id=S.id;S.id='';candidates(id)}}
async function candidates(leadId){const d=await api(`/v1.2/dispatch-pool/${encodeURIComponent(leadId)}/candidates`);const rows=(d.candidates||[]).map(x=>`<tr><td>${esc(x.company_name)}<br><small>${esc(x.company_id)}</small></td><td>${x.eligible?badge('APPROVED'):badge('REJECTED')}</td><td>${x.points_price}</td><td>${x.points_available??'按权限隐藏'}</td><td>${esc((x.exclusion_reasons||[]).join('、')||'符合条件')}</td><td>${x.eligible?`<button class="ops-btn primary" data-dispatch="${x.company_id}">派发</button>`:'--'}</td></tr>`);modal('选择接收公司',table(['公司','资格','价格','可用积分','判断','操作'],rows),()=>document.querySelectorAll('[data-dispatch]').forEach(b=>b.onclick=()=>dispatchOne(leadId,b.dataset.dispatch)))}
async function dispatchOne(leadId,companyId){const note=prompt('派发备注（可选）','')||'';try{await api(`/v1.2/dispatch-pool/${encodeURIComponent(leadId)}/dispatch`,{method:'POST',body:JSON.stringify({company_id:companyId,idempotency_key:`dispatch-${crypto.randomUUID()}`,note:note||null})});toast('客资已派发');closeModal();dispatch()}catch(e){toast(e.message,true)}}
async function returns(){const [d,t]=await Promise.all([api(`/v1.2/returns${qs({page:S.page,page_size:20})}`),can('verification.read')?api('/v1.2/return-verifications/tasks?page=1&page_size=100'):Promise.resolve({items:[]})]);const rows=(d.items||[]).map(x=>`<tr><td>${esc(x.id)}<br><small>${esc(x.assignment_id)}</small></td><td>${esc(label(x.reason_code))}</td><td>${badge(x.status)}</td><td>${esc(x.company_id)}</td><td>${fmt(x.submitted_at||x.created_at)}</td><td><button class="ops-btn" data-return="${x.id}">详情/终审</button></td></tr>`);const tasks=(t.items||[]).map(x=>`<tr><td>${esc(x.id)}</td><td>${badge(x.status)}</td><td>${esc(x.assignee_user_id||'未分配')}</td><td>${esc(x.return_request_id||'--')}</td><td><button class="ops-btn" data-task="${x.id}">详情</button> <button class="ops-btn" data-assign="${x.id}">分配</button></td></tr>`);shell(`<section class="ops-card"><h2>退回申诉</h2>${table(['申诉/派发单','原因','状态','公司','时间','操作'],rows)}${pager(d)}</section>${can('verification.read')?`<section class="ops-card"><h2>后置核验任务</h2>${table(['任务','状态','核验人','申诉','操作'],tasks)}</section>`:''}`);bindPager(d,returns);document.querySelectorAll('[data-return]').forEach(b=>b.onclick=()=>returnDetail(b.dataset.return));document.querySelectorAll('[data-task]').forEach(b=>b.onclick=()=>taskDetail(b.dataset.task));document.querySelectorAll('[data-assign]').forEach(b=>b.onclick=()=>assignTask(b.dataset.assign));if(S.id){const id=S.id;S.id='';returnDetail(id)}}
async function returnDetail(id){const x=await api(`/v1.2/returns/${encodeURIComponent(id)}`);modal('退回申诉详情',`<div class="ops-detail-grid">${[['申诉ID',x.id],['派发单',x.assignment_id],['客资ID',x.lead_id],['状态',label(x.status)],['原因',label(x.reason_code)],['核验任务',x.verification_task_id],['申诉截止',fmt(x.appeal_deadline_at)],['终审说明',x.final_decision_reason]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>事实与证据</h3><p>${esc(x.description||'--')}</p><pre class="ops-code">${esc(JSON.stringify(x.evidences||[],null,2))}</pre></section>${can('return.review')&&['REVIEWING','NEED_MORE_EVIDENCE'].includes(x.status)?'<div class="ops-actions"><button class="ops-btn primary" data-final="APPROVE">通过</button><button class="ops-btn danger" data-final="REJECT">驳回</button><button class="ops-btn" data-final="NEED_MORE">补证</button></div>':''}`,()=>document.querySelectorAll('[data-final]').forEach(b=>b.onclick=()=>finalReview(id,b.dataset.final)))}
async function finalReview(id,decision){const note=prompt('请输入终审说明（至少 2 个字符）','')||'';if(note.trim().length<2)return toast('终审说明不足',true);try{await api(`/v1.2/returns/${encodeURIComponent(id)}/final-review`,{method:'POST',body:JSON.stringify({decision,note:note.trim()})});toast('终审完成');closeModal();returns()}catch(e){toast(e.message,true)}}
async function taskDetail(id){const x=await api(`/v1.2/return-verifications/tasks/${encodeURIComponent(id)}`);modal('核验任务详情',`<pre class="ops-code">${esc(JSON.stringify(x,null,2))}</pre>`)}
async function assignTask(id){const assignee_user_id=prompt('请输入电销用户 ID','')||'';if(!assignee_user_id)return;try{await api(`/v1.2/return-verifications/tasks/${encodeURIComponent(id)}/assign`,{method:'POST',body:JSON.stringify({assignee_user_id})});toast('任务已分配');returns()}catch(e){toast(e.message,true)}}
async function rewards(){const [d,r]=await Promise.all([api(`/v1.2/supplier-rewards${qs({page:S.page,page_size:20})}`),can('reward.manage')?api('/v1.2/admin/supplier-reward-rules/current'):Promise.resolve(null)]);const rows=(d.items||[]).map(x=>`<tr><td>${esc(x.id)}<br><small>${esc(x.assignment_id)}</small></td><td>${esc(x.supplier_company_id)}</td><td>${x.claim_points}</td><td>${x.reward_points}</td><td>${badge(x.status)}</td><td>${fmt(x.reward_due_at)}</td><td><button class="ops-btn" data-reward="${x.id}">详情</button>${can('reward.manage')&&x.status==='OBSERVING'?` <button class="ops-btn primary" data-settle="${x.id}">结算</button>`:''}${can('reward.reverse')&&x.status==='SETTLED'?` <button class="ops-btn danger" data-reverse="${x.id}">冲正</button>`:''}</td></tr>`);shell(`${r?`<section class="ops-card"><h2>当前奖励规则</h2><pre class="ops-code">${esc(JSON.stringify(r,null,2))}</pre><button class="ops-btn" id="new-rule">新建规则版本</button> <button class="ops-btn gold" id="settle-due">执行到期结算</button></section>`:''}<section class="ops-card"><h2>供应商奖励</h2>${table(['奖励/派发单','供应商','领取积分','奖励积分','状态','应结算','操作'],rows)}${pager(d)}</section>`);bindPager(d,rewards);document.querySelectorAll('[data-reward]').forEach(b=>b.onclick=()=>rewardDetail(b.dataset.reward));document.querySelectorAll('[data-settle]').forEach(b=>b.onclick=()=>settle(b.dataset.settle));document.querySelectorAll('[data-reverse]').forEach(b=>b.onclick=()=>reverse(b.dataset.reverse));document.querySelector('#settle-due')?.addEventListener('click',settleDue);document.querySelector('#new-rule')?.addEventListener('click',newRule);if(S.id){const id=S.id;S.id='';rewardDetail(id)}}
async function rewardDetail(id){const x=await api(`/v1.2/supplier-rewards/${encodeURIComponent(id)}`);modal('奖励详情',`<div class="ops-detail-grid">${[['奖励ID',x.id],['客资ID',x.lead_id],['派发单',x.assignment_id],['供应商',x.supplier_company_id],['接收公司',x.receiver_company_id],['状态',label(x.status)],['奖励积分',x.reward_points],['规则版本',x.rule_version]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><pre class="ops-code">${esc(JSON.stringify(x.rule_snapshot||{},null,2))}</pre><button class="ops-btn" id="trace">业务追踪</button>`,()=>document.querySelector('#trace').onclick=()=>{closeModal();go('audit',id)})}
async function settle(id){try{await api(`/v1.2/admin/supplier-rewards/${encodeURIComponent(id)}/settle`,{method:'POST'});toast('结算指令已执行');rewards()}catch(e){toast(e.message,true)}}
async function settleDue(){try{await api('/v1.2/admin/supplier-rewards/settle-due',{method:'POST',body:JSON.stringify({limit:500})});toast('到期奖励结算已执行');rewards()}catch(e){toast(e.message,true)}}
async function reverse(id){const note=prompt('冲正说明（至少 5 个字符）','')||'';if(note.trim().length<5)return toast('冲正说明不足',true);try{await api(`/v1.2/admin/supplier-rewards/${encodeURIComponent(id)}/reverse`,{method:'POST',body:JSON.stringify({reason_code:'ADMIN_ERROR',note:note.trim()})});toast('奖励已冲正');rewards()}catch(e){toast(e.message,true)}}
async function newRule(){const ratio=Number(prompt('奖励比例（基点）','3000')||3000);try{await api('/v1.2/admin/supplier-reward-rules',{method:'POST',body:JSON.stringify({ratio_bps:ratio,min_points:0,max_points:null,hard_duplicate_days:90,reward_duplicate_days:180,historical_suspect_days:365,publish_immediately:true})});toast('规则版本已创建并发布');rewards()}catch(e){toast(e.message,true)}}
async function audit(){const business=S.id||'';const d=await api(`/v1.2/audit-events${qs({page:S.page,page_size:50,business_id:business})}`);const rows=(d.items||[]).map(x=>`<tr><td>${fmt(x.created_at)}</td><td>${esc(x.action)}<br><small>${esc(x.actor_user_id||'system')}</small></td><td>${esc(x.resource_type)}<br><small>${esc(x.resource_id||'--')}</small></td><td>${esc(x.company_id||'--')}</td><td>${esc(x.request_id||'--')}</td></tr>`);shell(`<div class="ops-filter"><input class="ops-input" id="business" placeholder="输入业务 ID" value="${esc(business)}"><button class="ops-btn primary" id="query">查询审计</button><button class="ops-btn gold" id="trace" ${business?'':'disabled'}>全链路追踪</button></div><section class="ops-card"><h2>审计事件</h2>${table(['时间','动作','资源','公司','请求ID'],rows)}${pager(d)}</section>`);bindPager(d,audit);document.querySelector('#query').onclick=()=>go('audit',document.querySelector('#business').value.trim());document.querySelector('#trace').onclick=()=>trace(document.querySelector('#business').value.trim());if(S.id){const id=S.id;S.id='';trace(id)}}
async function trace(id){if(!id)return;try{const d=await api(`/v1.2/trace/${encodeURIComponent(id)}`);modal('业务全链路追踪',`<div class="ops-detail-grid">${[['查询ID',d.business_id],['关联ID',d.linked_ids?.length],['派发单',d.assignments?.length],['退回',d.returns?.length],['奖励',d.supplier_rewards?.length],['核验任务',d.verification_tasks?.length],['通知',d.notifications?.length],['审计事件',d.audit_events?.length]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b??0)}</b></div>`).join('')}</div><pre class="ops-code">${esc(JSON.stringify(d,null,2))}</pre>`)}catch(e){toast(e.message,true)}}
function redirectToAllowedSurface(){
  const systemLink=visibleSystemLinks()[0];
  if(systemLink){location.replace(systemLink.href);return true}
  if(can('lead.manual.manage')||can('lead.supplier.review')){location.replace('./v12-leads.html');return true}
  const roles=new Set(S.me?.roles||[]);
  if(roles.has('TELESALES')){location.replace('/call/');return true}
  if(roles.has('FRANCHISE_OWNER')){location.replace('/h5/');return true}
  return false;
}
function renderNoAccess(){zsSetSafeHtml(app, `<div class="ops-standalone"><section class="ops-card"><h1>当前账号无管理后台权限</h1><p class="ops-muted">请使用与当前身份匹配的工作台，或联系超级管理员核对角色。</p><a class="ops-btn" href="./index.html">返回登录页</a></section></div>`)}
async function boot(){
  try{
    S.me=await api('/auth/me');
    if(!syncRouteFromUrl({canonicalize:true})){
      if(!redirectToAllowedSurface())renderNoAccess();
      return;
    }
    render();
  }catch{location.href='./index.html'}
}
window.addEventListener('popstate',()=>{if(syncRouteFromUrl())render()});
boot();
