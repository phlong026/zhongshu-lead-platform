const API='/api/v1',app=document.querySelector('#app'),toastEl=document.querySelector('#toast'),modalRoot=document.querySelector('#modal-root');
const S={me:null,view:'overview',id:'',status:'',page:1,companyStatus:'PENDING',companyCapabilityPage:1,companyAreaPage:1,telesalesUsers:null};
const P={overview:['工作台','layout-dashboard',['*','dashboard.operation.read']],leads:['客资','user-check',['*','lead.supplier.review']],telesales:['电销','phone',['*','verification.read']],dispatch:['派发','hand-claim',['*','lead.dispatch']],companies:['加盟商','building',['*','company.profile.review','company.account.manage']],returns:['异常','rotate-ccw',['*','return.read']],finance:['资金','coins',['*']],audit:['审计','search',['*','audit.read']]};
const ROLE_HOME_CONTRACT={SUPER_ADMIN:'系统治理',OPERATION:'今日运营'};
const ROLE_HOME_PRIORITY=['SUPER_ADMIN','OPERATION'];
const ADMIN_ROLE_HOME_CONTENT={
  SUPER_ADMIN:{title:'系统治理',subtitle:'聚焦高风险待办、加盟商治理、资金处理与完整审计。',cards:['风险预警','加盟商账号','资金异常','高风险审计']},
  OPERATION:{title:'今日运营',subtitle:'聚焦待初审、待派发、待电销结论、退回终审与加盟商治理。',cards:['待初审','待派发','待电销结论','待终审','加盟商待审']},
};
const L={DRAFT:'待完善',IMPORTED:'待补信息',IMPORT_ERROR:'导入异常',DUPLICATE_REVIEW:'疑似重复',PENDING:'待审核',PENDING_REVIEW:'待初审',PENDING_TELESALES_VERIFY:'待电销核验',PENDING_OPERATION_DISPOSITION:'待运营处置',READY_DISPATCH:'待派发',PENDING_CLAIM:'待领取',CLAIMED:'已领取',SUBMITTED:'已提交',VERIFYING:'核验中',REVIEWING:'待终审',NEED_MORE_EVIDENCE:'待补证',APPROVED:'已通过',REJECTED:'已驳回',OBSERVING:'观察期',FROZEN:'已冻结',SETTLED:'已结算',CANCELLED:'已取消',REVERSED:'已撤销',ACTIVE:'已启用',DISABLED:'已停用',ASSIGNED:'待处理',IN_PROGRESS:'核验中',QUALIFIED:'信息合格',INFO_INCOMPLETE:'信息不全',UNVERIFIABLE:'无法核验',INVALID:'信息无效',CLEAR:'无重复',DUPLICATE:'疑似重复',PLATFORM_MANUAL:'平台录入',SUPPLIER_H5:'加盟商提交',EMPTY_NUMBER:'空号或停机',OUT_OF_SERVICE_REGION:'超出服务区域',DUPLICATE_TO_RECEIVER:'接收方重复客户',NON_HOUSING_CONSULTATION:'非建房装修咨询',CONNECTED:'已接通',NO_ANSWER:'无人接听',OUT_OF_SERVICE:'停机',WRONG_PERSON:'非本人',REFUSED:'拒接或拒访',OTHER:'其他',SUPPORT_RETURN:'支持退回',DOES_NOT_SUPPORT_RETURN:'不支持退回',INCONCLUSIVE:'信息不足',RECHARGE:'充值',ADJUST:'人工调整',REVERSE:'冲正'};
Object.assign(L,{FOLLOWING:'跟进中',RETURN_PENDING:'退回处理中',RETURNED:'已退回',RELEASED:'已释放',EXPIRED:'已过期',COMPLETED:'已完成',CLOSED:'已关闭',UNCONTACTED:'未联系',CONTACTED:'已联系',INTERESTED:'有意向',NOT_INTERESTED:'无意向',DEAL:'已成交',INVALID:'无效'});
const EVIDENCE_LABEL={CHAT_SCREENSHOT:'沟通截图',CALL_RECORDING:'通话录音'};
const AUDIT_ACTION_LABEL={AUTH_LOGIN:'登录账号',AUTH_LOGOUT:'退出账号',FOLLOWUP_CREATE:'记录客户跟进',WECHAT_OAUTH_START_FAILED:'微信授权未完成',COMPANY_ACCOUNT_CREATE:'开通加盟商账号',COMPANY_ACCOUNT_ENABLE:'启用加盟商账号',COMPANY_ACCOUNT_DISABLE:'停用加盟商账号',COMPANY_ACCOUNT_PASSWORD_RESET:'重置加盟商账号密码',POINTS_RECHARGE:'加盟商积分充值',V12_COMPANY_CAPABILITY_REQUEST:'提交加盟商能力申请',V12_PLATFORM_LEAD_DRAFT_CREATE:'新建平台客资草稿',V12_PLATFORM_LEAD_DRAFT_UPDATE:'更新平台客资草稿',V12_PLATFORM_LEAD_SUBMIT:'提交平台客资',V12_SUPPLIER_LEAD_DRAFT_CREATE:'新建加盟商客资草稿',V12_SUPPLIER_LEAD_DRAFT_UPDATE:'更新加盟商客资草稿',V12_SUPPLIER_LEAD_SUBMIT:'提交加盟商客资',V12_SUPPLIER_LEAD_REVIEW:'初审加盟商客资',V12_PRE_DISPATCH_VERIFY_ASSIGN:'派发前置电销核验',V12_PRE_DISPATCH_VERIFY_START:'开始前置电销核验',V12_PRE_DISPATCH_DIAL_CLICK:'拨打前置核验电话',V12_PRE_DISPATCH_VERIFY_SUBMIT:'提交前置核验结论',V12_PRE_DISPATCH_DISPOSITION:'运营处置前置核验结论',V12_DEDUP_OVERRIDE:'确认客资不重复',V12_MANUAL_DISPATCH:'人工派发客资',V12_ASSIGNMENT_CLAIM:'领取客资',V12_RETURN_DRAFT_SAVE:'保存退回草稿',V12_RETURN_EVIDENCE_UPLOAD:'上传申诉证据',V12_RETURN_EVIDENCE_READ:'查看申诉证据',V12_RETURN_SUBMIT:'提交退回申诉',V12_RETURN_VERIFY_ASSIGN:'分配电话核验',V12_RETURN_VERIFY_CLAIM:'领取电话核验',V12_RETURN_VERIFY_DIAL:'拨打核验电话',V12_RETURN_VERIFY_SUBMIT:'提交电话核验',V12_RETURN_FINAL_REVIEW:'完成退回终审',V12_SUPPLIER_REWARD_RULE_CREATE:'新建奖励规则',V12_SUPPLIER_REWARD_RULE_PUBLISH:'发布奖励规则',V12_SUPPLIER_REWARD_SETTLE:'结算供客奖励',V12_SUPPLIER_REWARD_SETTLE_DUE:'批量结算到期奖励',V12_SUPPLIER_REWARD_REVERSE:'撤销供客奖励'};
const AUDIT_RESOURCE_LABEL={user:'账号',lead:'客资',assignment:'派发单',calendar_day:'工作日历',company:'加盟商公司',company_capability:'加盟商能力',company_lead_capability:'加盟商客资能力',company_service_area:'服务区域',company_service_area_v12:'服务区域',dictionary:'业务选项',followup:'跟进记录',invite:'加盟邀请',job:'系统任务',lead_price_rule:'客资积分规则',notification:'消息',outbox:'通知任务',points_account:'积分账户',points_ledger:'积分记录',points_package:'充值档位',rbac:'账号权限',return_evidence:'申诉证据',return_request:'退回申诉',supplier_lead_reward:'供客奖励',supplier_reward:'供客奖励',supplier_reward_batch:'奖励批次',supplier_reward_rule:'供客奖励规则',sync_batch:'客资导入批次',system_config:'规则配置',verification_task:'电话核验任务',verification_template:'电话核验内容',wechat_bind:'微信绑定'};
const EXCLUSION_REASON_LABEL={COMPANY_INACTIVE:'加盟商当前未启用',RECEIVER_CAPABILITY_REQUIRED:'尚未开通接收客资能力',SELF_SUPPLY_FORBIDDEN:'不能接收自己提交的客资',SERVICE_REGION_MISMATCH:'服务区域不匹配',DUPLICATE_TO_RECEIVER:'接收方已有相同客户',POINTS_INSUFFICIENT:'可用积分不足'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const TECHNICAL_CODE=/^(?:[A-Z][A-Z0-9_]{2,}|[a-z][a-z0-9]*|[a-z0-9]+(?:[_-][a-z0-9]+)+)$/;
const readableLabel=(value,fallback='待确认')=>{const text=String(value??'').trim();if(!text)return fallback;return L[text]||(TECHNICAL_CODE.test(text)?fallback:text)};
const recordCode=(value,prefix='记录')=>{const text=String(value??'').replace(/-/g,'');return text?`${prefix}-${text.slice(-8).toUpperCase()}`:'--'};
const fmt=v=>v?new Date(v).toLocaleString('zh-CN'):'--',can=p=>(S.me?.permissions||[]).some(x=>x==='*'||x===p),label=v=>readableLabel(v);
const verificationTaskLabel=task=>task?.status==='PENDING'&&!task?.assignee_user_id?'待分配':label(task?.status);
const auditAction=v=>AUDIT_ACTION_LABEL[v]||readableLabel(v,'其他业务操作'),auditResource=v=>AUDIT_RESOURCE_LABEL[v]||readableLabel(v,'业务记录');
const candidateReasons=reasons=>(reasons||[]).map(reason=>EXCLUSION_REASON_LABEL[reason]||readableLabel(reason,'其他条件暂不符合')).join('、')||'符合条件';
const icon=name=>window.ZSIconSystem?.svg?.(name)||'';
const badge=v=>`<span class="ops-status ${['APPROVED','SETTLED','CLAIMED'].includes(v)?'ok':['REJECTED','CANCELLED','REVERSED'].includes(v)?'bad':'warn'}">${esc(label(v))}</span>`;
const verificationTaskBadge=task=>`<span class="ops-status warn">${esc(verificationTaskLabel(task))}</span>`;
const qs=o=>{const p=new URLSearchParams;Object.entries(o).forEach(([k,v])=>v!==''&&v!=null&&p.set(k,v));return p.toString()?`?${p}`:''};
async function api(path,opt={}){const h={...(opt.headers||{})};if(opt.body&&!(opt.body instanceof FormData))h['Content-Type']='application/json';const r=await fetch(API+path,{...opt,headers:h,credentials:'include'});let j={};try{j=await r.json()}catch{}if(!r.ok||j.code!=='OK')throw new Error(j.message||'请求失败');return j.data}
function toast(m,e=false){toastEl.textContent=m;toastEl.className=`ops-toast show ${e?'error':''}`;clearTimeout(toast.t);toast.t=setTimeout(()=>toastEl.className='ops-toast',2400)}
function closeModal(){modalRoot.innerHTML=''}
function modal(title,body,bind){zsSetSafeHtml(modalRoot, `<div class="ops-overlay"><section class="ops-modal"><div class="ops-modal-head"><h2>${esc(title)}</h2><button class="ops-btn" id="modal-close">关闭</button></div>${body}</section></div>`);document.querySelector('#modal-close').onclick=closeModal;bind?.()}
function actionForm(options,onSubmit){
  const {title,message='',labelText='处理说明',value='',required=false,minLength=0,inputType='textarea',submitLabel='确认提交',danger=false,validate}=options;
  const control=inputType==='number'
    ?`<input class="ops-input" id="action-value" type="number" value="${esc(value)}" inputmode="decimal">`
    :`<textarea class="ops-textarea" id="action-value" placeholder="请填写${esc(labelText)}">${esc(value)}</textarea>`;
  modal(title,`<form class="ops-form" id="action-form">${message?`<div class="ops-notice">${esc(message)}</div>`:''}<div class="ops-field"><label for="action-value">${esc(labelText)}${required?' *':''}</label>${control}<small class="ops-muted" id="action-hint">${required?`至少填写 ${minLength||1} 个字符`:'可选填写，便于后续追溯'}</small></div><div class="ops-actions"><button type="button" class="ops-btn" id="action-cancel">取消</button><button class="ops-btn ${danger?'danger':'primary'}" id="action-submit">${esc(submitLabel)}</button></div></form>`,()=>{
    const form=document.querySelector('#action-form'),input=document.querySelector('#action-value'),submit=document.querySelector('#action-submit');
    document.querySelector('#action-cancel').onclick=closeModal;
    form.onsubmit=async event=>{
      event.preventDefault();
      const raw=input.value.trim();
      const validationMessage=(required&&raw.length<Math.max(1,minLength))?`请至少填写 ${Math.max(1,minLength)} 个字符`:validate?.(raw);
      if(validationMessage){toast(validationMessage,true);input.focus();return}
      submit.disabled=true;
      try{await onSubmit(raw);closeModal()}catch(error){submit.disabled=false;toast(error.message,true)}
    };
    input.focus();
  });
}
function allowed(meta){return meta[2].some(can)}
function primaryRole(){const roles=new Set(S.me?.roles||[]);return ROLE_HOME_PRIORITY.find(role=>roles.has(role))||''}
function nav(){return Object.entries(P).filter(([,m])=>allowed(m)).map(([k,m])=>`<button class="${S.view===k?'active':''}" data-view="${k}"><span>${icon(m[1])}</span><span>${m[0]}</span></button>`).join('')}
function shell(body){
  const meta=P[S.view]||P.overview;
  const roleHome=ADMIN_ROLE_HOME_CONTENT[primaryRole()];
  const pageTitle=S.view==='overview'&&roleHome?roleHome.title:meta[0];
  const pageSubtitle=S.view==='overview'&&roleHome?'角色专属首页':'客资运营管理';
  const setting=primaryRole()==='SUPER_ADMIN'?`<button class="ops-btn" data-view="companies" type="button">${icon('settings')}设置</button>`:'';
  zsSetSafeHtml(app, `<div class="ops-shell"><aside class="ops-side"><div class="ops-brand"><img class="ops-logo" src="./logo.png" alt="合家美宅"><div><strong>合家美宅</strong><small>V1.2 统一工作台</small></div></div><div class="ops-menu-label">业务工作台</div><nav class="ops-menu">${nav()}</nav><div class="ops-side-foot"><b>${esc(S.me?.display_name||'')}</b><br><span>${esc(ROLE_HOME_CONTRACT[primaryRole()]||'')}</span></div></aside><section class="ops-main"><header class="ops-top"><div class="ops-title"><h1>${esc(pageTitle)}</h1><p>${esc(pageSubtitle)}</p></div><div class="ops-top-actions"><button class="ops-btn primary" id="refresh">${icon('rotate-ccw')}刷新</button>${setting}<button class="ops-btn" id="logout" type="button">${icon('log-out')}退出</button></div></header><main class="ops-content">${body}</main></section></div>`);
  document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>go(button.dataset.view));
  document.querySelector('#refresh').onclick=render;
  document.querySelector('#logout').onclick=async()=>{await api('/auth/logout',{method:'POST'}).catch(()=>{});location.replace('/admin/')};
}
function firstAllowedView(){return Object.keys(P).find(view=>allowed(P[view]))||''}
function syncRouteFromUrl({canonicalize=false}={}){
  const url=new URL(location.href);
  const requestedView=url.searchParams.get('view')||'overview';
  const nextView=P[requestedView]&&allowed(P[requestedView])?requestedView:firstAllowedView();
  if(!nextView)return false;
  S.view=nextView;
  S.id=url.searchParams.get('id')||'';
  S.status=url.searchParams.get('status')||'';
  S.page=1;
  if(canonicalize&&requestedView!==nextView){
    url.searchParams.set('view',nextView);
    url.searchParams.delete('id');
    history.replaceState(null,'',url);
  }
  return true;
}
function go(view,id=''){
  if(!P[view]||!allowed(P[view])||(S.view===view&&S.id===id&&!S.status))return;
  const url=new URL(location.href);
  url.searchParams.set('view',view);
  id?url.searchParams.set('id',id):url.searchParams.delete('id');
  url.searchParams.delete('status');
  history.pushState(null,'',url);
  syncRouteFromUrl();
  render();
}
function table(head,rows){return `<div class="ops-table-wrap"><table class="ops-table"><thead><tr>${head.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.join('')||`<tr><td colspan="${head.length}" class="ops-empty">暂无数据</td></tr>`}</tbody></table></div>`}
function pager(d){const pages=Math.max(1,Math.ceil((d.total||0)/(d.page_size||20)));return `<div class="ops-pager"><button class="ops-btn" id="prev" ${S.page<=1?'disabled':''}>上一页</button><span>${S.page}/${pages}，共 ${d.total||0} 条</span><button class="ops-btn" id="next" ${S.page>=pages?'disabled':''}>下一页</button></div>`}
function bindPager(d,fn){const pages=Math.max(1,Math.ceil((d.total||0)/(d.page_size||20)));document.querySelector('#prev')?.addEventListener('click',()=>{S.page--;fn()});document.querySelector('#next')?.addEventListener('click',()=>{S.page=Math.min(pages,S.page+1);fn()})}
function statusSummary(data,hrefForStatus){return `<div class="ops-detail-grid">${Object.entries(data||{}).map(([status,count])=>{const content=`<small>${esc(label(status))}</small><b>${Number(count||0)}</b><i aria-hidden="true">${icon('chevron-right')}</i>`;const href=typeof hrefForStatus==='function'?hrefForStatus(status):hrefForStatus;return href?`<a class="ops-detail ops-detail-link" href="${esc(href)}" aria-label="${esc(label(status))} ${Number(count||0)} 条，查看明细">${content}</a>`:`<div class="ops-detail">${content}</div>`}).join('')||'<div class="ops-empty">暂无状态数据</div>'}</div>`}
function fileSize(bytes){const value=Number(bytes||0);if(value<1024)return `${value} B`;if(value<1024*1024)return `${(value/1024).toFixed(1)} KB`;return `${(value/1024/1024).toFixed(1)} MB`}
function evidenceList(items){
  return (items||[]).map(item=>{
    const url=item.access_token?`${API}/v1.2/return-evidences/${encodeURIComponent(item.id)}/download?token=${encodeURIComponent(item.access_token)}`:'';
    const isImage=item.type==='CHAT_SCREENSHOT'||String(item.mime_type||'').startsWith('image/');
    const isAudio=item.type==='CALL_RECORDING'||String(item.mime_type||'').startsWith('audio/');
    const preview=!url?'':isImage?`<a class="ops-evidence-preview" target="_blank" rel="noopener" href="${esc(url)}"><img src="${esc(url)}" alt="${esc(item.original_name||'沟通截图')}" loading="lazy"></a><a class="ops-btn" target="_blank" rel="noopener" href="${esc(url)}">在线查看截图</a>`:isAudio?`<audio controls preload="metadata" src="${esc(url)}">当前浏览器不支持在线播放录音。</audio><a class="ops-btn" target="_blank" rel="noopener" href="${esc(url)}">在线播放录音</a>`:`<a class="ops-btn" target="_blank" rel="noopener" href="${esc(url)}">查看文件</a>`;
    return `<article class="ops-detail ops-evidence-card"><small>${esc(EVIDENCE_LABEL[item.type]||'申诉证据')}</small><b>${esc(item.original_name||'未命名文件')}</b><p>${esc(fileSize(item.file_size))} · ${fmt(item.created_at)}</p>${preview}</article>`;
  }).join('')||'<div class="ops-empty">暂无证据</div>';
}
function telesalesName(userId){if(!userId)return '未分配';const user=(S.telesalesUsers||[]).find(item=>item.id===userId);return user?.display_name||user?.username||'已分配'}
async function loadTelesalesUsers(){if(!S.telesalesUsers)S.telesalesUsers=await api('/admin-meta/telesales-users');return S.telesalesUsers}
async function render(){
  shell('<div class="ops-loading">加载中…</div>');
  const views={overview,leads:review,telesales,dispatch,companies,returns,finance,audit};
  try{await (views[S.view]||overview)()}catch(error){shell(`<div class="ops-error">${esc(error.message)}</div>`);toast(error.message,true)}
}
const totalOf=values=>Object.values(values||{}).reduce((sum,value)=>sum+Number(value||0),0);
const countStatus=(items,statuses)=>items.filter(item=>statuses.includes(item.status)).length;
function roleMetricCards(cards){return `<div class="ops-grid ops-role-metrics">${cards.map(([name,value,iconName,href])=>{const content=`<i>${icon(iconName)}</i><small>${esc(name)}</small><b>${esc(value??0)}</b>`;return href?`<a class="ops-kpi" href="${href}">${content}</a>`:`<div class="ops-kpi">${content}</div>`}).join('')}</div>`}
function roleHome(content,cards,body=''){shell(`<section class="ops-role-hero"><div><span>今日工作面</span><h2>${esc(content.title)}</h2><p>${esc(content.subtitle)}</p></div><div class="ops-role-mark">${icon('layout-dashboard')}</div></section>${roleMetricCards(cards)}${body}`)}
async function overview(){
  const role=primaryRole();
  const [report,preDispatch,returnRequests]=await Promise.all([
    api('/v1.2/reports/overview'),
    api('/v1.2/pre-dispatch-verifications/tasks?page=1&page_size=200'),
    api('/v1.2/returns?page=1&page_size=200'),
  ]);
  const preDispatchItems=preDispatch.items||[];
  const returnItems=returnRequests.items||[];
  const cards=role==='SUPER_ADMIN'
    ?[
      ['加盟商治理','管理','building','?view=companies'],
      ['资金处理','进入','coins','?view=finance'],
      ['业务审计','查看','search','?view=audit'],
      ['待运营处置',countStatus(preDispatchItems,['SUBMITTED']),'phone','?view=telesales'],
    ]
    :[
      ['待初审',report.leads.by_status?.PENDING_REVIEW||0,'user-check','?view=leads'],
      ['待电销派发',countStatus(preDispatchItems,['ASSIGNED']),'phone','?view=telesales'],
      ['待电销结论',countStatus(preDispatchItems,['SUBMITTED']),'clipboard-check','?view=telesales'],
      ['待派发',report.leads.by_status?.READY_DISPATCH||0,'hand-claim','?view=dispatch'],
      ['待退回终审',countStatus(returnItems,['REVIEWING']),'rotate-ccw','?view=returns'],
      ['加盟商待审','进入','building','?view=companies'],
    ];
  const operationRows=[
    ['加盟商客资初审',report.leads.by_status?.PENDING_REVIEW||0,'核对资料完整性、重复线索与服务区域','leads'],
    ['前置电销待派发',countStatus(preDispatchItems,['ASSIGNED']),'任务必须由运营派发给指定电销人员','telesales'],
    ['前置电销待处置',countStatus(preDispatchItems,['SUBMITTED']),'电销提交事实结论后，由运营决定进入派发池、补充或关闭','telesales'],
    ['退回终审',countStatus(returnItems,['REVIEWING']),'核验结论只作为事实依据，最终退款与后续动作由运营决定','returns'],
  ];
  const body=`<section class="ops-card"><div class="ops-card-head"><div><h2>运营待办</h2><p>所有状态变更均保留审计记录；电销不具备自主领取或决定后续处置的入口。</p></div></div>${table(['事项','数量','处理责任','操作'],operationRows.map(([name,count,description,view])=>`<tr><td><b>${esc(name)}</b></td><td>${esc(count)}</td><td>${esc(description)}</td><td><button class="ops-btn" data-overview-view="${view}">查看</button></td></tr>`))}</section>`;
  roleHome(ADMIN_ROLE_HOME_CONTENT[role],cards,body);
  document.querySelectorAll('[data-overview-view]').forEach(button=>button.onclick=()=>go(button.dataset.overviewView));
}
async function review(){
  const data=await api(`/v1.2/admin/supplier-leads${qs({page:S.page,page_size:20})}`);
  const rows=(data.items||[]).map(lead=>{
    const pending=lead.review_status==='PENDING';
    const actions=[`<button class="ops-btn" data-detail="${esc(lead.id)}">详情</button>`];
    if(pending){
      actions.push(`<button class="ops-btn primary" data-review="${esc(lead.id)}:QUALIFIED">确认合格</button>`);
      actions.push(`<button class="ops-btn" data-review-info="${esc(lead.id)}">信息不全并派发电销</button>`);
      actions.push(`<button class="ops-btn" data-review="${esc(lead.id)}:DUPLICATE">标记重复</button>`);
      actions.push(`<button class="ops-btn danger" data-review="${esc(lead.id)}:INVALID">明确无效</button>`);
    }
    return `<tr><td><b>${esc(lead.customer_name)}</b><br>${esc(lead.phone_masked||'--')}</td><td>${esc(lead.city||'--')} ${esc(lead.district||'')}</td><td>${badge(lead.status)} ${badge(lead.review_status)}</td><td>${esc(label(lead.duplicate_status))}</td><td>${fmt(lead.submitted_at)}</td><td>${actions.join(' ')}</td></tr>`;
  });
  shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>加盟商客资初审</h2><p>列表只展示脱敏手机号。信息不足时必须派发给指定电销人员，不能由电销自行领取。</p></div></div>${table(['客户','区域','状态','去重','提交时间','操作'],rows)}${pager(data)}</section>`);
  bindPager(data,review);
  document.querySelectorAll('[data-detail]').forEach(button=>button.onclick=()=>reviewDetail(button.dataset.detail));
  document.querySelectorAll('[data-review]').forEach(button=>button.onclick=()=>{
    const [id,decision]=button.dataset.review.split(':');
    reviewAction(id,decision);
  });
  document.querySelectorAll('[data-review-info]').forEach(button=>button.onclick=()=>assignInitialPreDispatch(button.dataset.reviewInfo));
  if(S.id){const id=S.id;S.id='';reviewDetail(id)}
}
async function reviewDetail(id){const x=await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(id)}`);modal('客资初审详情',`<div class="ops-detail-grid">${[['客资编号',recordCode(x.id,'KZ')],['客户',x.customer_name],['手机号',x.phone_masked],['处理状态',label(x.status)],['初审结果',label(x.review_status)],['重复检查',label(x.duplicate_status)],['服务地区',`${x.city||''} ${x.district||''}`]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>客户需求</h3><p class="ops-muted">${esc(x.need_summary||'暂无说明')}</p></section><button class="ops-btn" id="trace">查看完整记录</button>`,()=>document.querySelector('#trace').onclick=()=>{closeModal();go('audit',id)})}
function reviewAction(id,decision){const copy={QUALIFIED:['确认客资合格','资料完整且不需要电话补充，将进入待派发池。',false,false],DUPLICATE:['标记重复客资','请写明重复判断依据，客资将进入重复核查。',true,false],INVALID:['确认客资无效','请写明无效原因，加盟商可根据说明补正后重新提交。',true,true]}[decision];actionForm({title:copy[0],message:copy[1],labelText:'初审说明',required:copy[2],minLength:2,submitLabel:'确认提交',danger:copy[3]},async note=>{await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(id)}/review`,{method:'POST',body:JSON.stringify({decision,note:note||null})});toast('初审结果已提交');await review()})}
async function assignInitialPreDispatch(leadId){
  try{
    const users=await loadTelesalesUsers();
    const options=users.map(user=>`<option value="${esc(user.id)}">${esc(user.display_name||user.username)}${user.username?` · ${esc(user.username)}`:''}</option>`).join('');
    modal('信息不全并派发电销',users.length?`<form class="ops-form" id="initial-pre-dispatch-form"><div class="ops-notice">初审结论会同步记录为“信息不全”；电销只能接受运营指定的任务。</div><div class="ops-field"><label for="initial-pre-assignee">电销人员 *</label><select class="ops-input" id="initial-pre-assignee">${options}</select></div><div class="ops-field"><label for="initial-pre-note">初审说明 *</label><textarea class="ops-textarea" id="initial-pre-note" placeholder="说明哪些资料不足"></textarea></div><div class="ops-field"><label for="initial-pre-reason">核验重点 *</label><textarea class="ops-textarea" id="initial-pre-reason" placeholder="例如：确认客户意向、预算和可联系时间"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="initial-pre-cancel">取消</button><button class="ops-btn primary" id="initial-pre-submit">确认派发</button></div></form>`:'<div class="ops-empty">暂无可分配的电销人员</div>',()=>{
      const form=document.querySelector('#initial-pre-dispatch-form');
      if(!form)return;
      document.querySelector('#initial-pre-cancel').onclick=closeModal;
      form.onsubmit=async event=>{
        event.preventDefault();
        const note=document.querySelector('#initial-pre-note').value.trim();
        const reason=document.querySelector('#initial-pre-reason').value.trim();
        const submit=document.querySelector('#initial-pre-submit');
        if(note.length<2||reason.length<2){toast('请至少填写 2 个字的初审说明和核验重点',true);return}
        submit.disabled=true;
        try{
          await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(leadId)}/review`,{method:'POST',body:JSON.stringify({decision:'INFO_INCOMPLETE',note,assignee_user_id:document.querySelector('#initial-pre-assignee').value,pre_dispatch_reason:reason})});
          toast('已记录初审结论并派发电销核验');
          closeModal();
          await review();
        }catch(error){submit.disabled=false;toast(error.message,true)}
      };
    });
  }catch(error){toast(error.message,true)}
}
async function assignPreDispatch(leadId){
  try{
    const users=await loadTelesalesUsers();
    const options=users.map(user=>`<option value="${esc(user.id)}">${esc(user.display_name||user.username)}${user.username?` · ${esc(user.username)}`:''}</option>`).join('');
    modal('派发前置电销核验',users.length?`<form class="ops-form" id="pre-dispatch-form"><div class="ops-notice">电销只能处理运营派发的任务；提交结论后由运营决定后续处置。</div><div class="ops-field"><label for="pre-dispatch-assignee">电销人员 *</label><select class="ops-input" id="pre-dispatch-assignee">${options}</select></div><div class="ops-field"><label for="pre-dispatch-reason">派发原因 *</label><textarea class="ops-textarea" id="pre-dispatch-reason" placeholder="例如：客户意向、区域或联系方式需要电话核实"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="pre-dispatch-cancel">取消</button><button class="ops-btn primary" id="pre-dispatch-submit">确认派发</button></div></form>`:'<div class="ops-empty">暂无可分配的电销人员</div>',()=>{
      const form=document.querySelector('#pre-dispatch-form');
      if(!form)return;
      document.querySelector('#pre-dispatch-cancel').onclick=closeModal;
      form.onsubmit=async event=>{
        event.preventDefault();
        const reason=document.querySelector('#pre-dispatch-reason').value.trim();
        const submit=document.querySelector('#pre-dispatch-submit');
        if(reason.length<2){toast('请至少填写 2 个字的派发原因',true);return}
        submit.disabled=true;
        try{
          await api(`/v1.2/admin/leads/${encodeURIComponent(leadId)}/pre-dispatch-verification`,{method:'POST',body:JSON.stringify({assignee_user_id:document.querySelector('#pre-dispatch-assignee').value,reason})});
          toast('前置电销核验已派发');
          closeModal();
          await review();
        }catch(error){submit.disabled=false;toast(error.message,true)}
      };
    });
  }catch(error){toast(error.message,true)}
}
async function telesales(){
  const data=await api(`/v1.2/pre-dispatch-verifications/tasks${qs({page:S.page,page_size:20})}`);
  await loadTelesalesUsers();
  const rows=(data.items||[]).map(task=>{
    const lead=task.lead||{};
    const nextStep=task.is_overdue?'已超时，需运营改派':task.status==='SUBMITTED'?'运营处置电销结论':'电销完成事实核验';
    const action=task.status==='SUBMITTED'
      ?`<button class="ops-btn primary" data-pre-disposition="${esc(task.lead_id)}">运营处置</button>`
      :`<button class="ops-btn" data-pre-assign="${esc(task.lead_id)}">${task.assignee_user_id?'改派':'派发'}</button>`;
    return `<tr><td><b>${esc(lead.customer_name||'待核验客户')}</b><br><small>${esc(lead.phone_masked||'--')}</small></td><td>${verificationTaskBadge(task)}</td><td>${esc(telesalesName(task.assignee_user_id))}</td><td>${esc(label(task.conclusion))}</td><td>${esc(nextStep)}</td><td>${fmt(task.due_at)}</td><td>${action}</td></tr>`;
  });
  shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>前置电销核验</h2><p>运营在此分配或改派；仅已提交结论的任务可由运营决定进入派发池、退回补充、标记重复或关闭。超时任务需改派后重新核验。</p></div></div>${table(['客户','任务状态','电销人员','事实结论','下一步','核验截止','操作'],rows)}${pager(data)}</section>`);
  bindPager(data,telesales);
  document.querySelectorAll('[data-pre-assign]').forEach(button=>button.onclick=()=>assignPreDispatch(button.dataset.preAssign));
  document.querySelectorAll('[data-pre-disposition]').forEach(button=>button.onclick=()=>disposePreDispatch(button.dataset.preDisposition));
}
function disposePreDispatch(leadId){
  modal('运营处置电销结论',`<form class="ops-form" id="pre-disposition-form"><div class="ops-notice">电销只提供核验事实；后续流转由运营负责并留存说明。</div><div class="ops-field"><label for="pre-disposition-decision">后续处理 *</label><select class="ops-input" id="pre-disposition-decision"><option value="APPROVE_POOL">确认合格，进入派发池</option><option value="RETURN_REWORK">资料待补，退回补充</option><option value="DUPLICATE">标记为重复客资</option><option value="CLOSE">关闭该客资</option></select></div><div class="ops-field"><label for="pre-disposition-note">运营处理说明 *</label><textarea class="ops-textarea" id="pre-disposition-note" placeholder="写明结合电销结论作出的处理判断"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="pre-disposition-cancel">取消</button><button class="ops-btn primary" id="pre-disposition-submit">确认处置</button></div></form>`,()=>{
    const form=document.querySelector('#pre-disposition-form');
    document.querySelector('#pre-disposition-cancel').onclick=closeModal;
    form.onsubmit=async event=>{
      event.preventDefault();
      const note=document.querySelector('#pre-disposition-note').value.trim();
      const submit=document.querySelector('#pre-disposition-submit');
      if(note.length<2){toast('请至少填写 2 个字的运营处理说明',true);return}
      submit.disabled=true;
      try{
        await api(`/v1.2/admin/leads/${encodeURIComponent(leadId)}/pre-dispatch-disposition`,{method:'POST',body:JSON.stringify({decision:document.querySelector('#pre-disposition-decision').value,note})});
        toast('运营处置已提交');
        closeModal();
        await telesales();
      }catch(error){submit.disabled=false;toast(error.message,true)}
    };
  });
}
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
  const [companyPage,capabilities,areas]=await Promise.all([
    api('/companies?page=1&page_size=200'),
    api(`/v1.2/admin/company-capabilities${qs({review_status:S.companyStatus,page:S.companyCapabilityPage,page_size:20})}`),
    api(`/v1.2/admin/service-areas${qs({review_status:S.companyStatus,page:S.companyAreaPage,page_size:20})}`),
  ]);
  const companyAssignmentSummary=summary=>{
    const byStatus=summary?.by_status||{};
    const statuses=Object.entries(byStatus).map(([status,count])=>`${label(status)} ${Number(count||0)} 条`).join('、');
    return `<small>共 ${Number(summary?.total||0)} 条</small><br><small>${esc(statuses||'暂无已派发客资')}</small>`;
  };
  const companyRows=(companyPage.items||[]).map(company=>`<tr><td><b>${esc(company.name)}</b><br><small>${esc(company.code)}</small></td><td>${badge(company.status)}</td><td>${companyAssignmentSummary(company.assignment_summary)}</td><td>${esc(company.owner_name||'--')}</td><td><button class="ops-btn primary" data-company-accounts="${esc(company.id)}" data-company-name="${esc(company.name)}">管理账号</button></td></tr>`);
  const capabilityRows=(capabilities.items||[]).map(item=>`<tr><td><b>${esc(item.company_name)}</b><br><small>${esc(recordCode(item.company_id,'加盟商'))}</small></td><td>${esc(CAPABILITY_LABEL[item.capability_code]||readableLabel(item.capability_code,'其他能力'))}</td><td>${badge(item.review_status)}<br><small>${item.active?'已启用':'未启用'}</small></td><td>${esc(cleanProfileNote(item.review_note)||'--')}</td><td>${fmt(item.reviewed_at)}</td><td>${capabilityReviewActions(item)} <button class="ops-btn" data-company-accounts="${esc(item.company_id)}" data-company-name="${esc(item.company_name)}">账号</button></td></tr>`);
  const areaRows=(areas.items||[]).map(item=>{const removal=String(item.review_note||'').startsWith('[REMOVE_REQUEST]');return `<tr><td><b>${esc(item.company_name)}</b><br><small>${esc(recordCode(item.company_id,'加盟商'))}</small></td><td>${esc(item.region_name||recordCode(item.region_code,'区域'))}<br><small>${esc(item.is_primary_city?'主要城市':readableLabel(item.region_level,'服务区域'))}</small></td><td>${badge(item.review_status)}<br><small>${removal&&item.active?'待移除，当前仍生效':item.active?'已生效':'未生效'}</small></td><td>${esc(cleanProfileNote(item.review_note)||'--')}</td><td>${fmt(item.reviewed_at)}</td><td>${areaReviewActions(item)}</td></tr>`});
  shell(`<section class="ops-card company-review"><div class="ops-card-head"><div><h2>加盟商公司与账号</h2><p>运营只查看公司级状态（客资汇总）和账号生命周期，不查看加盟商内部员工的客资分配明细。</p></div></div>${table(['加盟商','公司状态','公司客资状态','负责人','操作'],companyRows)}</section><section class="ops-card company-review"><div class="ops-card-head"><div><h2>加盟商能力与服务区域审核申请</h2><p>供客与接收能力独立审核；区域移除申请在批准前继续保持原服务资格。</p></div><select class="ops-input" id="company-review-status" style="width:auto"><option value="PENDING" ${S.companyStatus==='PENDING'?'selected':''}>待审核</option><option value="APPROVED" ${S.companyStatus==='APPROVED'?'selected':''}>已通过</option><option value="REJECTED" ${S.companyStatus==='REJECTED'?'selected':''}>已驳回</option></select></div><h3>公司能力（${capabilities.total||0}）</h3>${table(['加盟商','能力','状态','审核说明','审核时间','操作'],capabilityRows)}${companyQueuePager(capabilities,'capability',S.companyCapabilityPage)}</section><section class="ops-card company-review"><h3>服务区域（${areas.total||0}）</h3>${table(['加盟商','区域','状态','审核说明','审核时间','操作'],areaRows)}${companyQueuePager(areas,'area',S.companyAreaPage)}</section>`);
  document.querySelector('#company-review-status').onchange=event=>{S.companyStatus=event.target.value;S.companyCapabilityPage=1;S.companyAreaPage=1;companies()};
  bindCompanyQueuePager(capabilities,'capability','companyCapabilityPage');
  bindCompanyQueuePager(areas,'area','companyAreaPage');
  document.querySelectorAll('[data-cap-decision]').forEach(button=>button.onclick=()=>reviewCompanyCapability(button));
  document.querySelectorAll('[data-area-decision]').forEach(button=>button.onclick=()=>reviewCompanyArea(button));
  document.querySelectorAll('[data-company-accounts]').forEach(button=>button.onclick=()=>companyAccounts(button.dataset.companyAccounts,button.dataset.companyName));
}
async function reviewCompanyCapability(button){
  const decision=button.dataset.capDecision;
  actionForm({title:decision==='REJECT'?'驳回或停用公司能力':'通过公司能力',message:'能力状态会影响加盟商能否供应或接收客资。',labelText:'审核说明',required:decision==='REJECT',minLength:2,submitLabel:decision==='REJECT'?'确认驳回或停用':'确认通过',danger:decision==='REJECT'},async note=>{await api(`/v1.2/admin/companies/${encodeURIComponent(button.dataset.capCompany)}/capabilities/${encodeURIComponent(button.dataset.capCode)}/review`,{method:'POST',body:JSON.stringify({decision,note:note||null})});toast('公司能力审核已完成');await companies()});
}
async function reviewCompanyArea(button){
  const decision=button.dataset.areaDecision;
  actionForm({title:decision==='REJECT'?'驳回服务区域':'通过服务区域',message:'移除申请在审核通过前仍保持原服务资格。',labelText:'审核说明',required:decision==='REJECT',minLength:2,submitLabel:decision==='REJECT'?'确认驳回':'确认通过',danger:decision==='REJECT'},async note=>{await api(`/v1.2/admin/service-areas/${encodeURIComponent(button.dataset.areaId)}/review`,{method:'POST',body:JSON.stringify({decision,note:note||null})});toast('服务区域审核已完成');await companies()});
}
const COMPANY_ACCOUNT_ROLE_LABEL={FRANCHISE_OWNER:'加盟商负责人',FRANCHISE_EMPLOYEE:'加盟商员工'};
const isSuperAdmin=()=>primaryRole()==='SUPER_ADMIN';
async function companyAccounts(companyId,companyName){
  try{
    const accounts=await api(`/companies/${encodeURIComponent(companyId)}/accounts`);
    const rows=accounts.map(account=>{
      const action=account.status==='ACTIVE'?'DISABLED':'ACTIVE';
      const actionLabel=action==='ACTIVE'?'启用':'停用';
      return `<tr><td><b>${esc(account.display_name)}</b><br><small>${esc(account.username||'--')}</small></td><td>${esc(COMPANY_ACCOUNT_ROLE_LABEL[account.role_code]||account.role_code||'--')}</td><td>${badge(account.status)}</td><td>${account.wechat_bound?'已绑定':'未绑定'}</td><td><button class="ops-btn" data-company-account-status="${esc(companyId)}:${esc(account.id)}:${action}">${actionLabel}</button> <button class="ops-btn" data-company-account-reset="${esc(companyId)}:${esc(account.id)}">重置密码</button></td></tr>`;
    });
    modal(`${companyName||'加盟商'}账号`,`${isSuperAdmin()?'<div class="ops-notice">超级管理员的开通、停用和重置操作必须填写理由，并写入审计。</div>':'<div class="ops-notice">运营可开通、停用和重置该加盟商的负责人及员工账号，所有操作均留存审计。</div>'}<div class="ops-actions"><button class="ops-btn primary" id="company-account-create">开通账号</button></div>${table(['姓名 / 登录账号','角色','状态','微信','操作'],rows)}`,()=>{
      document.querySelector('#company-account-create').onclick=()=>createCompanyAccount(companyId,companyName);
      document.querySelectorAll('[data-company-account-status]').forEach(button=>button.onclick=()=>{
        const [targetCompanyId,userId,status]=button.dataset.companyAccountStatus.split(':');
        changeCompanyAccountStatus(targetCompanyId,userId,status,companyName);
      });
      document.querySelectorAll('[data-company-account-reset]').forEach(button=>button.onclick=()=>{
        const [targetCompanyId,userId]=button.dataset.companyAccountReset.split(':');
        resetCompanyAccountPassword(targetCompanyId,userId,companyName);
      });
    });
  }catch(error){toast(error.message,true)}
}
function createCompanyAccount(companyId,companyName){
  modal(`开通${companyName||'加盟商'}账号`,`<form class="ops-form" id="company-account-form"><div class="ops-notice">只需填写姓名和登录账号，系统会生成 8 位以上初始密码并在成功后仅展示一次。</div><div class="ops-field"><label for="company-account-name">姓名 *</label><input class="ops-input" id="company-account-name" maxlength="64"></div><div class="ops-field"><label for="company-account-username">登录账号 *</label><input class="ops-input" id="company-account-username" maxlength="64" autocomplete="off"></div><div class="ops-field"><label for="company-account-role">角色 *</label><select class="ops-input" id="company-account-role"><option value="FRANCHISE_OWNER">加盟商负责人</option><option value="FRANCHISE_EMPLOYEE">加盟商员工</option></select></div><div class="ops-field"><label for="company-account-reason">操作理由${isSuperAdmin()?' *':''}</label><textarea class="ops-textarea" id="company-account-reason" placeholder="${isSuperAdmin()?'请说明超级管理员代为开通的原因':'可选填写，便于后续追溯'}"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="company-account-cancel">取消</button><button class="ops-btn primary" id="company-account-submit">确认开通</button></div></form>`,()=>{
    const form=document.querySelector('#company-account-form');
    document.querySelector('#company-account-cancel').onclick=()=>companyAccounts(companyId,companyName);
    form.onsubmit=async event=>{
      event.preventDefault();
      const display_name=document.querySelector('#company-account-name').value.trim();
      const username=document.querySelector('#company-account-username').value.trim();
      const reason=document.querySelector('#company-account-reason').value.trim();
      const submit=document.querySelector('#company-account-submit');
      if(!display_name||!username){toast('请填写姓名和登录账号',true);return}
      if(isSuperAdmin()&&reason.length<2){toast('超级管理员操作必须填写至少 2 个字的理由',true);return}
      submit.disabled=true;
      try{
        const account=await api(`/companies/${encodeURIComponent(companyId)}/accounts`,{method:'POST',body:JSON.stringify({display_name,username,role_code:document.querySelector('#company-account-role').value,reason:reason||null})});
        showInitialPassword(account.initial_password,()=>companyAccounts(companyId,companyName));
      }catch(error){submit.disabled=false;toast(error.message,true)}
    };
  });
}
function changeCompanyAccountStatus(companyId,userId,status,companyName){
  const enabling=status==='ACTIVE';
  actionForm({title:enabling?'启用加盟商账号':'停用加盟商账号',message:enabling?'启用后该账号可重新登录。':'停用会使该账号的现有会话失效。',labelText:'操作理由',required:isSuperAdmin(),minLength:2,submitLabel:enabling?'确认启用':'确认停用',danger:!enabling},async reason=>{
    await api(`/companies/${encodeURIComponent(companyId)}/accounts/${encodeURIComponent(userId)}/${enabling?'enable':'disable'}`,{method:'POST',body:JSON.stringify({reason:reason||null})});
    toast(enabling?'账号已启用':'账号已停用');
    await companyAccounts(companyId,companyName);
  });
}
function resetCompanyAccountPassword(companyId,userId,companyName){
  actionForm({title:'重置加盟商账号密码',message:'系统会生成新的初始密码并仅展示一次；旧会话将立即失效。',labelText:'重置理由',required:isSuperAdmin(),minLength:2,submitLabel:'确认重置',danger:true},async reason=>{
    const account=await api(`/companies/${encodeURIComponent(companyId)}/accounts/${encodeURIComponent(userId)}/reset-password`,{method:'POST',body:JSON.stringify({reason:reason||null})});
    showInitialPassword(account.initial_password,()=>companyAccounts(companyId,companyName));
  });
}
function showInitialPassword(password,onClose){
  if(!password){toast('操作已完成，但未返回初始密码',true);onClose?.();return}
  modal('请安全交付初始密码',`<div class="ops-notice">初始密码仅在当前窗口展示一次，请立即复制并通过安全渠道交付账号本人。</div><div class="ops-detail"><small>初始密码</small><b id="initial-password">${esc(password)}</b></div><div class="ops-actions"><button class="ops-btn primary" id="copy-initial-password">复制密码</button><button class="ops-btn" id="initial-password-close">已保存</button></div>`,()=>{
    document.querySelector('#copy-initial-password').onclick=async()=>{
      try{await navigator.clipboard.writeText(password);toast('初始密码已复制')}catch{toast('浏览器不支持自动复制，请手动复制',true)}
    };
    document.querySelector('#initial-password-close').onclick=()=>{closeModal();onClose?.()};
  });
}
async function dispatch(){const d=await api(`/v1.2/dispatch-pool${qs({page:S.page,page_size:20})}`);const rows=(d.items||[]).map(x=>`<tr><td><b>${esc(x.customer_name)}</b><br>${esc(x.phone_masked||'--')}</td><td>${esc(x.city||'--')} ${esc(x.district||'')}</td><td>${esc(label(x.source_kind))}</td><td>${esc(x.need_summary||'--')}</td><td><button class="ops-btn primary" data-candidate="${x.id}">选择接收公司</button></td></tr>`);shell(`<section class="ops-card"><h2>待人工派发池</h2>${table(['客户','服务地区','客资来源','客户需求','操作'],rows)}${pager(d)}</section>`);bindPager(d,dispatch);document.querySelectorAll('[data-candidate]').forEach(b=>b.onclick=()=>candidates(b.dataset.candidate));if(S.id){const id=S.id;S.id='';candidates(id)}}
async function candidates(leadId){const d=await api(`/v1.2/dispatch-pool/${encodeURIComponent(leadId)}/candidates`);const rows=(d.candidates||[]).map(x=>`<tr><td>${esc(x.company_name)}</td><td>${x.eligible?badge('APPROVED'):badge('REJECTED')}</td><td>${x.points_price}</td><td>${x.points_available??'按权限隐藏'}</td><td>${esc(candidateReasons(x.exclusion_reasons))}</td><td>${x.eligible?`<button class="ops-btn primary" data-dispatch="${x.company_id}">派发</button>`:'--'}</td></tr>`);modal('选择接收公司',table(['接收公司','是否可派','所需积分','可用积分','判断说明','操作'],rows),()=>document.querySelectorAll('[data-dispatch]').forEach(b=>b.onclick=()=>dispatchOne(leadId,b.dataset.dispatch)))}
function dispatchOne(leadId,companyId){actionForm({title:'确认人工派发',message:'请再次核对接收公司。提交后会生成派发单并记录审计。',labelText:'派发备注',submitLabel:'确认派发'},async note=>{await api(`/v1.2/dispatch-pool/${encodeURIComponent(leadId)}/dispatch`,{method:'POST',body:JSON.stringify({company_id:companyId,idempotency_key:`dispatch-${crypto.randomUUID()}`,note:note||null})});toast('客资已派发');await dispatch()})}
async function returns(){const [d,t]=await Promise.all([api(`/v1.2/returns${qs({status:S.status,page:S.page,page_size:20})}`),can('verification.read')?api('/v1.2/return-verifications/tasks?page=1&page_size=100'):Promise.resolve({items:[]})]);if(can('verification.read'))await loadTelesalesUsers();const rows=(d.items||[]).map(x=>`<tr><td>${esc(recordCode(x.id,'TH'))}<br><small>派发编号 ${esc(recordCode(x.assignment_id,'PF'))}</small></td><td>${esc(label(x.reason_code))}</td><td>${badge(x.status)}</td><td>${fmt(x.submitted_at||x.created_at)}</td><td><button class="ops-btn" data-return="${x.id}">查看与审核</button></td></tr>`);const tasks=(t.items||[]).map(x=>{const r=x.return_request||{},lead=x.lead||{},nextStep=x.is_overdue?'已超时，需运营改派':'电销完成退回事实核验';return `<tr><td><b>${esc(lead.customer_name||'待核验客户')}</b><br><small>${esc(lead.phone_masked||'--')}</small></td><td>${verificationTaskBadge(x)}</td><td>${esc(telesalesName(x.assignee_user_id))}</td><td>${esc(label(r.reason_code))}</td><td>${esc(nextStep)}</td><td>${fmt(x.due_at)}</td><td><button class="ops-btn" data-task="${x.id}">查看</button> <button class="ops-btn" data-assign="${x.id}">${x.assignee_user_id?'重新分配':'分配人员'}</button></td></tr>`});const filterNotice=S.status?`<div class="ops-notice">当前筛选：${esc(label(S.status))} <button class="ops-btn" id="returns-clear">查看全部</button></div>`:'';shell(`${filterNotice}<section class="ops-card"><h2>退回申诉</h2>${table(['退回编号','退回原因','处理状态','申诉时间','操作'],rows)}${pager(d)}</section>${can('verification.read')?`<section class="ops-card"><h2>电话核验任务</h2><p>仅在加盟商发起退回申诉后进行电话核验。</p>${table(['客户','状态','核验人员','退回原因','下一步','核验截止','操作'],tasks)}</section>`:''}`);bindPager(d,returns);document.querySelector('#returns-clear')?.addEventListener('click',()=>go('returns'));document.querySelectorAll('[data-return]').forEach(b=>b.onclick=()=>returnDetail(b.dataset.return));document.querySelectorAll('[data-task]').forEach(b=>b.onclick=()=>taskDetail(b.dataset.task));document.querySelectorAll('[data-assign]').forEach(b=>b.onclick=()=>assignTask(b.dataset.assign));if(S.id){const id=S.id;S.id='';returnDetail(id)}}
async function returnDetail(id){const x=await api(`/v1.2/returns/${encodeURIComponent(id)}`);if(can('verification.read'))await loadTelesalesUsers();const verification=x.verification||{};modal('退回申诉详情',`<div class="ops-detail-grid">${[['退回编号',recordCode(x.id,'TH')],['派发编号',recordCode(x.assignment_id,'PF')],['处理状态',label(x.status)],['退回原因',label(x.reason_code)],['核验人员',telesalesName(verification.assignee_user_id)],['核验状态',label(verification.status)],['申诉截止',fmt(x.appeal_deadline_at)],['终审说明',x.final_decision_reason]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>申诉说明</h3><p>${esc(x.description||'暂无说明')}</p></section><section class="ops-card"><h3>申诉证据</h3><div class="ops-detail-grid">${evidenceList(x.evidences)}</div></section>${can('return.review')&&['REVIEWING','NEED_MORE_EVIDENCE'].includes(x.status)?'<div class="ops-actions"><button class="ops-btn primary" data-final="APPROVE">通过退回</button><button class="ops-btn danger" data-final="REJECT">驳回申诉</button><button class="ops-btn" data-final="NEED_MORE">要求补充证据</button></div>':''}`,()=>document.querySelectorAll('[data-final]').forEach(b=>b.onclick=()=>finalReview(id,b.dataset.final)))}
function finalReview(id,decision){const actionLabel={APPROVE:'通过退回',REJECT:'驳回申诉',NEED_MORE:'要求补充证据'}[decision]||'提交终审';actionForm({title:actionLabel,message:'终审会影响积分返还与申诉状态，请写明判断依据。',labelText:'终审说明',required:true,minLength:2,submitLabel:`确认${actionLabel}`,danger:decision==='REJECT'},async note=>{await api(`/v1.2/returns/${encodeURIComponent(id)}/final-review`,{method:'POST',body:JSON.stringify({decision,note})});toast('终审完成');await returns()})}
async function taskDetail(id){const x=await api(`/v1.2/return-verifications/tasks/${encodeURIComponent(id)}`);await loadTelesalesUsers();const r=x.return_request||{},lead=x.lead||{},evidenceTotal=Object.values(r.evidence_summary||{}).reduce((sum,count)=>sum+Number(count||0),0);modal('电话核验详情',`<div class="ops-detail-grid">${[['客户',lead.customer_name],['联系电话',lead.phone||lead.phone_masked],['服务地区',`${lead.city||''} ${lead.district||''}`],['任务状态',verificationTaskLabel(x)],['核验人员',telesalesName(x.assignee_user_id)],['退回原因',label(r.reason_code)],['证据数量',`${evidenceTotal} 份`],['核验截止',fmt(x.due_at)],['申诉截止',fmt(r.appeal_deadline_at)],['联系结果',label(x.contact_result)],['核验结论',label(x.conclusion)]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>申诉说明</h3><p>${esc(r.description||'暂无说明')}</p></section>`)}
async function assignTask(id){
  try{
    const users=await loadTelesalesUsers();
    const options=users.map(user=>`<option value="${esc(user.id)}">${esc(user.display_name||user.username)}${user.username?` · ${esc(user.username)}`:''}</option>`).join('');
    modal('派发退回电话核验',users.length?`<form class="ops-form" id="return-assignment-form"><div class="ops-notice">电销只核实事实，不决定是否退回加盟商。改派会记录原责任人、当前责任人与派发理由。</div><div class="ops-field"><label for="telesales-assignee">电销人员 *</label><select class="ops-input" id="telesales-assignee">${options}</select></div><div class="ops-field"><label for="return-assignment-reason">派发或改派原因 *</label><textarea class="ops-textarea" id="return-assignment-reason" placeholder="例如：原人员请假，交由另一位电销继续核验"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="return-assignment-cancel">取消</button><button class="ops-btn primary" id="confirm-assignment">确认分配</button></div></form>`:'<div class="ops-empty">暂无可分配的电销人员</div>',()=>{
      const form=document.querySelector('#return-assignment-form');
      if(!form)return;
      document.querySelector('#return-assignment-cancel').onclick=closeModal;
      form.onsubmit=async event=>{
        event.preventDefault();
        const reason=document.querySelector('#return-assignment-reason').value.trim();
        const submit=document.querySelector('#confirm-assignment');
        if(reason.length<2){toast('请至少填写 2 个字的派发或改派原因',true);return}
        submit.disabled=true;
        try{
          await api(`/v1.2/return-verifications/tasks/${encodeURIComponent(id)}/assign`,{method:'POST',body:JSON.stringify({assignee_user_id:document.querySelector('#telesales-assignee').value,reason})});
          toast('电话核验任务已分配');
          closeModal();
          await returns();
        }catch(error){submit.disabled=false;toast(error.message,true)}
      };
    });
  }catch(error){toast(error.message,true)}
}
async function finance(){
  const [companyPage,packages,ledgerPage]=await Promise.all([
    api('/companies?page=1&page_size=200'),
    api('/points/packages?active_only=true'),
    api('/points/ledgers?page=1&page_size=20'),
  ]);
  const companies=companyPage.items||[];
  const companyNames=new Map(companies.map(company=>[company.id,company.name]));
  const companyRows=companies.map(company=>`<tr><td><b>${esc(company.name)}</b><br><small>${esc(company.code)}</small></td><td>${badge(company.status)}</td><td>${esc(company.points_balance??0)}</td><td><button class="ops-btn primary" data-recharge-company="${esc(company.id)}">线下充值</button></td></tr>`);
  const ledgerRows=(ledgerPage.items||[]).map(ledger=>`<tr><td>${fmt(ledger.created_at)}</td><td>${esc(companyNames.get(ledger.company_id)||recordCode(ledger.company_id,'加盟商'))}</td><td>${esc(label(ledger.ledger_type))}</td><td>${esc(ledger.delta>0?`+${ledger.delta}`:ledger.delta)}</td><td>${esc(ledger.balance_after)}</td><td>${esc(ledger.external_reference||'--')}</td></tr>`);
  shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>加盟商积分账户</h2><p>仅超级管理员可执行充值。每笔充值需核实线下款项、填写外部凭据，并写入不可变积分流水与审计。</p></div></div>${table(['加盟商','状态','当前积分','操作'],companyRows)}</section><section class="ops-card"><h2>最近积分流水</h2>${table(['时间','加盟商','类型','变化','余额','外部凭据'],ledgerRows)}${pager(ledgerPage)}</section>`);
  bindPager(ledgerPage,finance);
  document.querySelectorAll('[data-recharge-company]').forEach(button=>button.onclick=()=>rechargeCompanyPoints(button.dataset.rechargeCompany,companies,packages));
}
function rechargeCompanyPoints(companyId,companies,packages){
  const company=companies.find(item=>item.id===companyId);
  const options=packages.map(item=>`<option value="${esc(item.id)}" data-cash="${Number(item.cash_amount_cents)}">${esc(item.name)} · ${Number(item.total_points)} 积分</option>`).join('');
  if(!options){toast('当前没有可用的积分充值档位，请先配置档位',true);return}
  modal(`为${company?.name||'加盟商'}充值积分`,`<form class="ops-form" id="recharge-form"><div class="ops-notice">请先完成线下收款核实。本操作无需第二位超级管理员复核，但会记录操作人、充值档位、外部凭据与审计。</div><div class="ops-field"><label for="recharge-package">充值档位 *</label><select class="ops-input" id="recharge-package">${options}</select></div><div class="ops-field"><label for="recharge-reference">外部收款凭据号 *</label><input class="ops-input" id="recharge-reference" minlength="3" maxlength="128" placeholder="例如：银行流水号或收款单号"></div><div class="ops-field"><label for="recharge-note">备注</label><textarea class="ops-textarea" id="recharge-note" maxlength="500" placeholder="可填写核实说明"></textarea></div><label class="ops-check"><input type="checkbox" id="recharge-confirmed"> 我已核实本笔线下款项</label><div class="ops-actions"><button class="ops-btn" type="button" id="recharge-cancel">取消</button><button class="ops-btn primary" id="recharge-submit">确认充值</button></div></form>`,()=>{
    const form=document.querySelector('#recharge-form');
    document.querySelector('#recharge-cancel').onclick=closeModal;
    form.onsubmit=async event=>{
      event.preventDefault();
      const packageSelect=document.querySelector('#recharge-package');
      const external_reference=document.querySelector('#recharge-reference').value.trim();
      const confirmed=document.querySelector('#recharge-confirmed').checked;
      const submit=document.querySelector('#recharge-submit');
      if(external_reference.length<3){toast('请填写至少 3 个字符的外部收款凭据号',true);return}
      if(!confirmed){toast('请确认已核实线下款项',true);return}
      submit.disabled=true;
      try{
        await api('/points/recharge',{method:'POST',body:JSON.stringify({company_id:companyId,package_id:packageSelect.value,cash_amount_cents:Number(packageSelect.selectedOptions[0].dataset.cash),external_reference,note:document.querySelector('#recharge-note').value.trim()||null,idempotency_key:`recharge-${crypto.randomUUID()}`,confirmed:true})});
        toast('积分充值已入账');
        closeModal();
        await finance();
      }catch(error){submit.disabled=false;toast(error.message,true)}
    };
  });
}
function ruleSummary(rule){const ratio=(Number(rule?.ratio_bps||0)/100).toFixed(2).replace(/\.00$/,'');const max=rule?.max_points==null?'不设上限':`${rule.max_points} 积分`;return `<div class="ops-detail-grid">${[['奖励比例',`${ratio}%`],['最低奖励',`${rule?.min_points||0} 积分`],['最高奖励',max],['同一客户短期重复',`${rule?.hard_duplicate_days||0} 天内不计奖励`],['再次获得奖励',`${rule?.reward_duplicate_days||0} 天后`],['历史记录提醒',`查看 ${rule?.historical_suspect_days||0} 天内记录`]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b)}</b></div>`).join('')}</div>`}
async function rewards(){const [d,r]=await Promise.all([api(`/v1.2/supplier-rewards${qs({page:S.page,page_size:20})}`),can('reward.manage')?api('/v1.2/admin/supplier-reward-rules/current'):Promise.resolve(null)]);const rows=(d.items||[]).map(x=>`<tr><td>${esc(recordCode(x.id,'JL'))}<br><small>派发编号 ${esc(recordCode(x.assignment_id,'PF'))}</small></td><td>${esc(recordCode(x.supplier_company_id,'加盟商'))}</td><td>${x.claim_points}</td><td>${x.reward_points}</td><td>${badge(x.status)}</td><td>${fmt(x.reward_due_at)}</td><td><button class="ops-btn" data-reward="${x.id}">查看</button>${can('reward.manage')&&x.status==='OBSERVING'?` <button class="ops-btn primary" data-settle="${x.id}">结算</button>`:''}${can('reward.reverse')&&x.status==='SETTLED'?` <button class="ops-btn danger" data-reverse="${x.id}">撤销奖励</button>`:''}</td></tr>`);shell(`${r?`<section class="ops-card"><h2>当前奖励规则</h2>${ruleSummary(r)}<div class="ops-actions"><button class="ops-btn" id="new-rule">调整奖励比例</button><button class="ops-btn gold" id="settle-due">结算已到期奖励</button></div></section>`:''}<section class="ops-card"><h2>供客奖励</h2>${table(['奖励编号','加盟商','领取积分','奖励积分','状态','预计结算','操作'],rows)}${pager(d)}</section>`);bindPager(d,rewards);document.querySelectorAll('[data-reward]').forEach(b=>b.onclick=()=>rewardDetail(b.dataset.reward));document.querySelectorAll('[data-settle]').forEach(b=>b.onclick=()=>settle(b.dataset.settle));document.querySelectorAll('[data-reverse]').forEach(b=>b.onclick=()=>reverse(b.dataset.reverse));document.querySelector('#settle-due')?.addEventListener('click',settleDue);document.querySelector('#new-rule')?.addEventListener('click',()=>newRule(r));if(S.id){const id=S.id;S.id='';rewardDetail(id)}}
async function rewardDetail(id){const x=await api(`/v1.2/supplier-rewards/${encodeURIComponent(id)}`);modal('奖励详情',`<div class="ops-detail-grid">${[['奖励编号',recordCode(x.id,'JL')],['派发编号',recordCode(x.assignment_id,'PF')],['加盟商',recordCode(x.supplier_company_id,'加盟商')],['接收公司',recordCode(x.receiver_company_id,'加盟商')],['状态',label(x.status)],['领取积分',x.claim_points],['奖励积分',x.reward_points],['预计结算',fmt(x.reward_due_at)],['实际到账',fmt(x.settled_at)]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>本笔奖励适用规则</h3>${ruleSummary(x.rule_snapshot||{})}</section><button class="ops-btn" id="trace">查看业务记录</button>`,()=>document.querySelector('#trace').onclick=()=>{closeModal();go('audit',id)})}
async function settle(id){try{await api(`/v1.2/admin/supplier-rewards/${encodeURIComponent(id)}/settle`,{method:'POST'});toast('结算指令已执行');rewards()}catch(e){toast(e.message,true)}}
async function settleDue(){try{await api('/v1.2/admin/supplier-rewards/settle-due',{method:'POST',body:JSON.stringify({limit:500})});toast('到期奖励结算已执行');rewards()}catch(e){toast(e.message,true)}}
function reverse(id){actionForm({title:'确认奖励冲正',message:'冲正会生成反向流水，不会修改或删除历史记录。',labelText:'冲正说明',required:true,minLength:5,submitLabel:'确认冲正',danger:true},async note=>{await api(`/v1.2/admin/supplier-rewards/${encodeURIComponent(id)}/reverse`,{method:'POST',body:JSON.stringify({reason_code:'ADMIN_ERROR',note})});toast('奖励已冲正');await rewards()})}
function newRule(currentRule){const currentRatio=Number(currentRule?.ratio_bps||0)/100;actionForm({title:'调整奖励比例',message:'新比例只影响规则发布后产生的奖励，历史奖励继续使用原规则。',labelText:'奖励比例（%）',value:String(currentRatio),inputType:'number',submitLabel:'发布新比例',validate:raw=>{const ratio=Number(raw);return Number.isFinite(ratio)&&ratio>0&&ratio<=100?'':'请输入 0 到 100 之间的奖励比例'}},async input=>{const ratio=Number(input);await api('/v1.2/admin/supplier-reward-rules',{method:'POST',body:JSON.stringify({ratio_bps:Math.round(ratio*100),min_points:currentRule.min_points,max_points:currentRule.max_points,hard_duplicate_days:currentRule.hard_duplicate_days,reward_duplicate_days:currentRule.reward_duplicate_days,historical_suspect_days:currentRule.historical_suspect_days,publish_immediately:true})});toast('奖励比例已更新');await rewards()})}
async function audit(){const business=S.id||'';const d=await api(`/v1.2/audit-events${qs({page:S.page,page_size:50,business_id:business})}`);const rows=(d.items||[]).map(x=>`<tr><td>${fmt(x.created_at)}</td><td>${esc(auditAction(x.action))}<br><small>${x.actor_user_id?`操作账号：${esc(recordCode(x.actor_user_id,'账号'))}`:'系统自动处理'}</small></td><td>${esc(auditResource(x.resource_type))}<br><small>业务记录：${esc(recordCode(x.resource_id,'业务'))}</small></td><td>${esc(recordCode(x.company_id,'加盟商'))}</td><td>${esc(recordCode(x.request_id,'操作'))}</td></tr>`);shell(`<div class="ops-filter"><input class="ops-input" id="business" placeholder="输入客资、派发单或申诉编号" value="${esc(business)}"><button class="ops-btn primary" id="query">查询操作记录</button><button class="ops-btn gold" id="trace" ${business?'':'disabled'}>查看完整记录</button></div><section class="ops-card"><h2>操作记录</h2>${table(['时间','处理动作','业务对象','加盟商','操作记录'],rows)}${pager(d)}</section>`);bindPager(d,audit);document.querySelector('#query').onclick=()=>go('audit',document.querySelector('#business').value.trim());document.querySelector('#trace').onclick=()=>trace(document.querySelector('#business').value.trim());if(S.id){const id=S.id;S.id='';trace(id)}}
async function trace(id){if(!id)return;try{const d=await api(`/v1.2/trace/${encodeURIComponent(id)}`);const timeline=(d.timeline||[]).map(item=>`<tr><td>${fmt(item.at)}</td><td>${esc(auditAction(item.action))}</td><td>${esc(auditResource(item.resource_type))}</td><td>${esc(recordCode(item.resource_id||item.id,'记录'))}</td></tr>`);modal('完整业务记录',`<div class="ops-detail-grid">${[['查询编号',recordCode(d.business_id,'业务')],['关联记录',d.linked_ids?.length],['派发单',d.assignments?.length],['退回申诉',d.returns?.length],['供应奖励',d.supplier_rewards?.length],['电话核验',d.verification_tasks?.length],['消息',d.notifications?.length],['操作记录',d.audit_events?.length]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b??0)}</b></div>`).join('')}</div><section class="ops-card"><h3>处理时间线</h3>${table(['时间','处理动作','业务对象','记录编号'],timeline)}</section>`)}catch(e){toast(e.message,true)}}
function redirectToAllowedSurface(){
  const roles=new Set(S.me?.roles||[]);
  if(roles.has('SUPER_ADMIN')||roles.has('OPERATION')){location.replace('/admin/v12-operations.html');return true}
  if(roles.has('TELESALES')){location.replace('/h5/call/');return true}
  if(roles.has('FRANCHISE_OWNER')||roles.has('FRANCHISE_EMPLOYEE')){location.replace('/h5/');return true}
  return false;
}
function renderLogin(message=''){
  zsSetSafeHtml(app, `<div class="ops-standalone"><section class="ops-card"><div class="ops-card-head"><div><h1>平台管理登录</h1><p>超级管理员和运营管理员登录后进入各自的统一工作台。</p></div></div>${message?`<div class="ops-notice">${esc(message)}</div>`:''}<form class="ops-form" id="platform-login-form"><div class="ops-field"><label for="username">登录账号</label><input class="ops-input" id="username" autocomplete="username" required></div><div class="ops-field"><label for="password">登录密码</label><input class="ops-input" id="password" type="password" autocomplete="current-password" required></div><div class="ops-actions"><button class="ops-btn primary" id="login-btn" type="submit">登录工作台</button></div></form></section></div>`);
  document.querySelector('#platform-login-form').onsubmit=async event=>{
    event.preventDefault();
    const submit=document.querySelector('#login-btn');
    submit.disabled=true;
    try{
      await api('/auth/login',{method:'POST',body:JSON.stringify({username:document.querySelector('#username').value.trim(),password:document.querySelector('#password').value})});
      location.replace('/admin/');
    }catch(error){submit.disabled=false;toast(error.message,true)}
  };
}
function renderNoAccess(){zsSetSafeHtml(app, `<div class="ops-standalone"><section class="ops-card"><h1>当前账号无管理后台权限</h1><p class="ops-muted">请使用与当前身份匹配的工作台，或联系超级管理员核对角色。</p><a class="ops-btn" href="/admin/">返回登录页</a></section></div>`)}
async function boot(){
  try{
    S.me=await api('/auth/me');
    if(!syncRouteFromUrl({canonicalize:true})){
      if(!redirectToAllowedSurface())renderNoAccess();
      return;
    }
    render();
  }catch(error){renderLogin(error.message||'请登录后继续')}
}
window.addEventListener('popstate',()=>{if(syncRouteFromUrl())render()});
boot();
