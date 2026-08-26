const API='/api/v1',app=document.querySelector('#app'),toastEl=document.querySelector('#toast'),modalRoot=document.querySelector('#modal-root');
const S={me:null,view:'overview',id:'',status:'',page:1,leadSource:'',platformLeads:[],supplierLeads:[],platformLeadPage:1,supplierLeadPage:1,financeRewardPage:1,financeCompanyKeyword:'',financeCompanyStatus:'',financeCompanyPage:1,financeCompanyId:'',financeLedgerType:'',platformCities:null,platformDistricts:[],companyKeyword:'',companyLifecycleStatus:'',companyPage:1,companyStatus:'PENDING',companyCapabilityPage:1,companyAreaPage:1,telesalesUsers:null,calendarMonth:''};
const P={overview:['首页','layout-dashboard',['*','dashboard.operation.read']],leads:['客资','user-check',['*','lead.manual.manage','lead.supplier.review']],telesales:['电销','phone',['*','verification.read']],dispatch:['派发','hand-claim',['*','lead.dispatch']],companies:['加盟商','building',['*','company.profile.review','company.account.manage']],returns:['异常','rotate-ccw',['*','return.read']],finance:['资金','coins',['*']],audit:['日志','search',['*','audit.read']],trace:['客资详情','file-text',['*','audit.read'],true],settings:['平台设置','settings',['*'],true],users:['内部账号','users',['*'],true],calendar:['工作日历','calendar',['*'],true],account:['账号中心','user',['*','dashboard.operation.read'],true]};
const ADMIN_VIEW_CONTRACT={SUPER_ADMIN:['overview','leads','companies','finance'],OPERATION:['overview','leads','telesales','dispatch','companies']};
const ROLE_HOME_PRIORITY=['SUPER_ADMIN','OPERATION'];
const ADMIN_ROLE_HOME_CONTENT={
  SUPER_ADMIN:{title:'经营总览',subtitle:'聚焦客资流转、经营异常、加盟商状态、资金风险与完整审计。',cards:['客资总量','异常待办','加盟商账号','资金风险']},
  OPERATION:{title:'今日运营',subtitle:'聚焦待初审、待派发、待电销结论、退回终审与加盟商治理。',cards:['待初审','待派发','待电销结论','待终审','加盟商待审']},
};
const ROLE_IDENTITY_LABEL={SUPER_ADMIN:'系统管理员',OPERATION:'运营人员',TELESALES:'电销人员',FRANCHISE_OWNER:'加盟商负责人',FRANCHISE_EMPLOYEE:'加盟商员工'};
const L={DRAFT:'待完善',IMPORTED:'待补信息',IMPORT_ERROR:'导入异常',DUPLICATE_REVIEW:'疑似重复',PENDING:'待审核',PENDING_REVIEW:'待初审',PENDING_TELESALES_VERIFY:'待电销核验',PENDING_OPERATION_DISPOSITION:'待运营处置',READY_DISPATCH:'待派发',PENDING_CLAIM:'待领取',WAITING_CLAIM:'等待领取',CLAIMED:'已领取',SUBMITTED:'已提交',VERIFYING:'核验中',REVIEWING:'待终审',NEED_MORE_EVIDENCE:'待补证',APPROVED:'已通过',REJECTED:'已驳回',OBSERVING:'观察期',FROZEN:'已冻结',SETTLED:'已结算',CANCELLED:'已取消',REVERSED:'已撤销',ACTIVE:'已启用',DISABLED:'已停用',ASSIGNED:'待处理',IN_PROGRESS:'核验中',QUALIFIED:'信息合格',INFO_INCOMPLETE:'信息不全',UNVERIFIABLE:'无法核验',INVALID:'信息无效',CLEAR:'无重复',DUPLICATE:'疑似重复',PLATFORM_MANUAL:'平台录入',SUPPLIER_H5:'加盟商提交',EMPTY_NUMBER:'空号或停机',OUT_OF_SERVICE_REGION:'超出服务区域',DUPLICATE_TO_RECEIVER:'接收方重复客户',NON_HOUSING_CONSULTATION:'非建房装修咨询',CONNECTED:'已接通',NO_ANSWER:'无人接听',OUT_OF_SERVICE:'停机',WRONG_PERSON:'非本人',REFUSED:'拒接或拒访',OTHER:'其他',SUPPORT_RETURN:'支持退回',DOES_NOT_SUPPORT_RETURN:'不支持退回',INCONCLUSIVE:'信息不足',RECHARGE:'充值',ADJUST:'人工调整',REVERSE:'冲正'};
Object.assign(L,{FOLLOWING:'跟进中',RETURN_PENDING:'退回处理中',RETURNED:'已退回',RELEASED:'已释放',EXPIRED:'已过期',COMPLETED:'已完成',CLOSED:'已关闭',UNCONTACTED:'未联系',CONTACTED:'已联系',INTERESTED:'有意向',NOT_INTERESTED:'无意向',DEAL:'已成交',INVALID:'无效'});
const EVIDENCE_LABEL={CHAT_SCREENSHOT:'沟通截图',CALL_RECORDING:'通话录音'};
const AUDIT_ACTION_LABEL={AUTH_LOGIN:'登录账号',AUTH_LOGOUT:'退出账号',AUTH_USERNAME_CHANGE:'修改登录账号',AUTH_USERNAME_CHANGE_FAILED:'修改登录账号失败',FOLLOWUP_CREATE:'记录客户跟进',WECHAT_OAUTH_START_FAILED:'微信授权未完成',COMPANY_CREATE:'创建加盟商主体',COMPANY_SIMPLE_CREATE:'快速创建加盟商主体',COMPANY_ACCOUNT_CREATE:'开通加盟商人员账号',COMPANY_ACCOUNT_ENABLE:'启用加盟商人员账号',COMPANY_ACCOUNT_DISABLE:'停用加盟商人员账号',COMPANY_ACCOUNT_PASSWORD_RESET:'重置加盟商人员账号密码',POINTS_RECHARGE:'加盟商积分充值',V12_COMPANY_CAPABILITY_REQUEST:'提交加盟商能力申请',V12_PLATFORM_LEAD_DRAFT_CREATE:'新建平台客资草稿',V12_PLATFORM_LEAD_DRAFT_UPDATE:'更新平台客资草稿',V12_PLATFORM_LEAD_SUBMIT:'提交平台客资',V12_SUPPLIER_LEAD_DRAFT_CREATE:'新建加盟商客资草稿',V12_SUPPLIER_LEAD_DRAFT_UPDATE:'更新加盟商客资草稿',V12_SUPPLIER_LEAD_SUBMIT:'提交加盟商客资',V12_SUPPLIER_LEAD_REVIEW:'初审加盟商客资',V12_PRE_DISPATCH_VERIFY_ASSIGN:'派发前置电销核验',V12_PRE_DISPATCH_VERIFY_START:'开始前置电销核验',V12_PRE_DISPATCH_DIAL_CLICK:'拨打前置核验电话',V12_PRE_DISPATCH_VERIFY_SUBMIT:'提交前置核验结论',V12_PRE_DISPATCH_DISPOSITION:'运营处置前置核验结论',V12_DEDUP_OVERRIDE:'确认客资不重复',V12_MANUAL_DISPATCH:'人工派发客资',V12_ASSIGNMENT_CLAIM:'领取客资',V12_RETURN_DRAFT_SAVE:'保存退回草稿',V12_RETURN_EVIDENCE_UPLOAD:'上传申诉证据',V12_RETURN_EVIDENCE_READ:'查看申诉证据',V12_RETURN_SUBMIT:'提交退回申诉',V12_RETURN_VERIFY_ASSIGN:'分配电话核验',V12_RETURN_VERIFY_CLAIM:'领取电话核验',V12_RETURN_VERIFY_DIAL:'拨打核验电话',V12_RETURN_VERIFY_SUBMIT:'提交电话核验',V12_RETURN_FINAL_REVIEW:'完成退回终审',V12_SUPPLIER_REWARD_RULE_CREATE:'新建奖励规则',V12_SUPPLIER_REWARD_RULE_PUBLISH:'发布奖励规则',V12_SUPPLIER_REWARD_SETTLE:'结算供客奖励',V12_SUPPLIER_REWARD_SETTLE_DUE:'批量结算到期奖励',V12_SUPPLIER_REWARD_REVERSE:'撤销供客奖励'};
Object.assign(AUDIT_ACTION_LABEL,{POINTS_ADJUST:'人工积分调账',POINTS_REVERSE:'人工积分冲正',POINTS_RECONCILE:'积分账目核对',NOTIFICATION_RETRY:'重新发送消息'});
Object.assign(AUDIT_ACTION_LABEL,{AUTH_PASSWORD_CHANGE:'修改登录密码',AUTH_PASSWORD_CHANGE_FAILED:'修改密码失败'});
const AUDIT_RESOURCE_LABEL={user:'账号',lead:'客资',assignment:'派发单',calendar_day:'工作日历',company:'加盟商公司',company_capability:'加盟商能力',company_lead_capability:'加盟商客资能力',company_service_area:'服务区域',company_service_area_v12:'服务区域',dictionary:'业务选项',followup:'跟进记录',invite:'加盟邀请',job:'系统任务',lead_price_rule:'客资积分规则',notification:'消息',outbox:'通知任务',points_account:'积分账户',points_ledger:'积分记录',points_package:'充值档位',rbac:'账号权限',return_evidence:'申诉证据',return_request:'退回申诉',supplier_lead_reward:'供客奖励',supplier_reward:'供客奖励',supplier_reward_batch:'奖励批次',supplier_reward_rule:'供客奖励规则',sync_batch:'客资导入批次',system_config:'规则配置',verification_task:'电话核验任务',verification_template:'电话核验内容',wechat_bind:'微信绑定'};
const EXCLUSION_REASON_LABEL={COMPANY_INACTIVE:'加盟商当前未启用',RECEIVER_CAPABILITY_REQUIRED:'尚未开通接收客资能力',SELF_SUPPLY_FORBIDDEN:'不能接收自己提交的客资',SERVICE_REGION_MISMATCH:'服务区域不匹配',DUPLICATE_TO_RECEIVER:'接收方已有相同客户',RETURNED_RECEIVER_EXCLUDED:'该公司曾领取后退回，默认不再次派发',POINTS_INSUFFICIENT:'可用积分不足'};
const NOTIFICATION_EVENT_LABEL={ASSIGNMENT_DISPATCHED:'客资派发提醒',INVITE_CREATED:'账号开通提醒',POINTS_RECHARGED:'积分到账提醒',V12_COMPANY_PROFILE_APPROVED:'加盟商审核结果',V12_SUPPLIER_LEAD_SUBMITTED:'客资提交提醒',V12_SUPPLIER_LEAD_REJECTED:'客资补正提醒'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const TECHNICAL_CODE=/^(?:[A-Z][A-Z0-9_]{2,}|[a-z][a-z0-9]*|[a-z0-9]+(?:[_-][a-z0-9]+)+)$/;
const readableLabel=(value,fallback='待确认')=>{const text=String(value??'').trim();if(!text)return fallback;return L[text]||(TECHNICAL_CODE.test(text)?fallback:text)};
const recordCode=(value,prefix='记录')=>{const text=String(value??'').replace(/-/g,'');return text?`${prefix}-${text.slice(-8).toUpperCase()}`:'--'};
const fmt=v=>v?new Date(v).toLocaleString('zh-CN'):'--',can=p=>(S.me?.permissions||[]).some(x=>x==='*'||x===p),label=v=>readableLabel(v);
const verificationTaskLabel=task=>task?.status==='PENDING'&&!task?.assignee_user_id?'待分配':label(task?.status);
const auditAction=v=>AUDIT_ACTION_LABEL[v]||readableLabel(v,'其他业务操作'),auditResource=v=>AUDIT_RESOURCE_LABEL[v]||readableLabel(v,'业务记录');
const notificationEventLabel=v=>NOTIFICATION_EVENT_LABEL[v]||'业务消息',notificationStatusLabel=v=>({FAILED:'发送未成功',DEAD:'发送已停止',MANUAL_ACTION_REQUIRED:'需要人工处理'}[v]||'等待处理');
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
function roleAllowsView(view){
  const role=primaryRole();
  if(view==='account'||view==='trace')return Boolean(role);
  if(['settings','users','calendar'].includes(view))return role==='SUPER_ADMIN';
  if(['returns','audit'].includes(view))return role==='SUPER_ADMIN'||role==='OPERATION';
  return Boolean(ADMIN_VIEW_CONTRACT[role]?.includes(view));
}
function canOpenView(view){return Boolean(P[view]&&allowed(P[view])&&roleAllowsView(view))}
function nav(){return (ADMIN_VIEW_CONTRACT[primaryRole()]||[]).filter(canOpenView).map(k=>{const m=P[k];return `<button class="${S.view===k?'active':''}" data-view="${k}"><span>${icon(m[1])}</span><span>${m[0]}</span></button>`}).join('')}
function shell(body){
  const accountName=S.me?.username||'当前账号';
  const identity=ROLE_IDENTITY_LABEL[primaryRole()]||'平台人员';
  zsSetSafeHtml(app, `<div class="ops-shell"><aside class="ops-side"><div class="ops-brand"><img class="ops-logo" src="./logo.png" alt="合家美宅"><div><strong>合家美宅统一工作台</strong><small>平台管理</small></div></div><div class="ops-menu-label">业务工作台</div><nav class="ops-menu">${nav()}</nav><div class="ops-account-zone"><button class="ops-account-card" data-account-center type="button"><i>${icon('user')}</i><span><b>${esc(accountName)}</b><small>${esc(identity)}</small></span></button></div></aside><section class="ops-main"><main class="ops-content">${body}</main></section></div>`);
  document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>go(button.dataset.view));
  document.querySelectorAll('[data-account-center]').forEach(button=>button.addEventListener('click',()=>go('account')));
}
function firstAllowedView(){return (ADMIN_VIEW_CONTRACT[primaryRole()]||[]).find(canOpenView)||''}
function syncRouteFromUrl({canonicalize=false}={}){
  const url=new URL(location.href);
  const requestedView=url.searchParams.get('view')||'overview';
  const nextView=canOpenView(requestedView)?requestedView:firstAllowedView();
  if(!nextView)return false;
  S.view=nextView;
  S.id=url.searchParams.get('id')||'';
  S.status=url.searchParams.get('status')||'';
  S.leadSource=url.searchParams.get('source')||'';
  S.page=1;
  if(canonicalize&&requestedView!==nextView){
    url.searchParams.set('view',nextView);
    url.searchParams.delete('id');
    history.replaceState(null,'',url);
  }
  return true;
}
function go(view,id=''){
  if(!canOpenView(view)||(S.view===view&&S.id===id&&!S.status))return;
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
  const views={overview,leads:review,telesales,dispatch,companies,returns,finance,audit,trace:fullTrace,settings,users:internalUsers,calendar,account};
  try{await (views[S.view]||overview)()}catch(error){shell(`<div class="ops-error">${esc(error.message)}</div>`);toast(error.message,true)}
}
const totalOf=values=>Object.values(values||{}).reduce((sum,value)=>sum+Number(value||0),0);
const countStatus=(items,statuses)=>items.filter(item=>statuses.includes(item.status)).length;
function roleMetricCards(cards){return `<div class="ops-grid ops-role-metrics">${cards.map(([name,value,iconName,href])=>{const content=`<i>${icon(iconName)}</i><small>${esc(name)}</small><b>${esc(value??0)}</b>`;return href?`<a class="ops-kpi" href="${href}">${content}</a>`:`<div class="ops-kpi">${content}</div>`}).join('')}</div>`}
function barChart(title,description,items){const max=Math.max(1,...items.map(([,value])=>Number(value||0)));return `<section class="ops-card ops-chart-card"><div class="ops-card-head"><div><h2>${esc(title)}</h2><p>${esc(description)}</p></div></div><div class="ops-bar-chart">${items.map(([name,value,view])=>`<button class="ops-bar-row" data-overview-view="${esc(view)}" type="button"><span>${esc(name)}</span><i><b style="width:${Math.max(3,Math.round(Number(value||0)/max*100))}%"></b></i><strong>${Number(value||0)}</strong></button>`).join('')}</div></section>`}
function roleHome(content,cards,body=''){shell(`<section class="ops-role-hero"><div><span>今日工作面</span><h2>${esc(content.title)}</h2><p>${esc(content.subtitle)}</p></div><div class="ops-role-mark">${icon('layout-dashboard')}</div></section>${roleMetricCards(cards)}${body}`)}
async function overview(){
  const role=primaryRole();
  const report=await api('/v1.2/reports/overview');
  const management=report.management||{};
  const pool=management.lead_pool||{};
  const verification=management.verification||{};
  const exceptions=management.exceptions||{};
  const cards=role==='SUPER_ADMIN'?[]
    :[
      ['待初审',report.leads.by_status?.PENDING_REVIEW||0,'user-check','?view=leads'],
      ['电销处理中',(verification.pending||0)+(verification.in_progress||0),'phone','?view=telesales'],
      ['待运营处置',verification.awaiting_operation||0,'clipboard-check','?view=telesales'],
      ['待派发',report.leads.by_status?.READY_DISPATCH||0,'hand-claim','?view=dispatch'],
      ['待退回终审',exceptions.return_final_review||0,'rotate-ccw','?view=returns'],
      ['加盟商待审',exceptions.company_review||0,'building','?view=companies'],
    ];
  if(role==='SUPER_ADMIN'){
    const funds=management.funds||{};
    const todoCount=(pool.unassigned||0)+(verification.pending||0)+(verification.in_progress||0)+(verification.awaiting_operation||0)+(exceptions.return_final_review||0)+(exceptions.company_review||0);
    const riskCount=(pool.problem||0)+(verification.overdue||0)+(exceptions.failed_notification||0)+(exceptions.disabled_company||0);
    cards.push(['客资总量',pool.total||0,'user-check','?view=leads'],['当前待办',todoCount,'clipboard-check','?view=leads'],['经营风险',riskCount,'alert-triangle','?view=returns'],['冻结供客奖励',funds.frozen_reward||0,'wallet','?view=finance']);
    const body=barChart('当前待办分布','只展示需要处理的业务队列；顶部数据用于判断整体规模与风险。',[['待派发',pool.unassigned||0,'leads'],['待电销核验',verification.pending||0,'leads'],['核验中',verification.in_progress||0,'leads'],['待运营处置',verification.awaiting_operation||0,'leads'],['退回终审',exceptions.return_final_review||0,'returns'],['加盟商待审',exceptions.company_review||0,'companies']]);
    roleHome(ADMIN_ROLE_HOME_CONTENT[role],cards,body);
    document.querySelectorAll('[data-overview-view]').forEach(button=>button.onclick=()=>go(button.dataset.overviewView));
    return;
  }
  const operationRows=[
    ['加盟商客资初审',report.leads.by_status?.PENDING_REVIEW||0,'核对资料完整性、重复线索与服务区域','leads'],
    ['电销正在核验',(verification.pending||0)+(verification.in_progress||0),'电销只核实事实；运营可改派超时或异常任务','telesales'],
    ['电销结论待处置',verification.awaiting_operation||0,'电销提交事实结论后，由运营决定进入派发池、补充或关闭','telesales'],
    ['待人工派发',report.leads.by_status?.READY_DISPATCH||0,'优先选择覆盖客资所在地且符合接收条件的加盟商','dispatch'],
    ['退回终审',exceptions.return_final_review||0,'核验结论只作为事实依据，最终退款与后续动作由运营决定','returns'],
    ['加盟商资料审核',exceptions.company_review||0,'能力与服务区域可一键通过；加盟商内部员工分配不在运营视图展示','companies'],
  ];
  const body=`<section class="ops-card"><div class="ops-card-head"><div><h2>今日待办</h2><p>按下一步责任人排列。电销不具备自主领取或决定后续处置的入口；加盟商内部员工分配仅由公司负责人处理。</p></div></div>${table(['待办事项','数量','下一步','操作'],operationRows.map(([name,count,description,view])=>`<tr><td><b>${esc(name)}</b></td><td>${esc(count)}</td><td>${esc(description)}</td><td><button class="ops-btn" data-overview-view="${view}">立即处理</button></td></tr>`))}</section>`;
  roleHome(ADMIN_ROLE_HOME_CONTENT[role],cards,body);
  document.querySelectorAll('[data-overview-view]').forEach(button=>button.onclick=()=>go(button.dataset.overviewView));
}
async function review(){
  const readOnly=primaryRole()==='SUPER_ADMIN';
  const canPlatform=can('lead.manual.manage');
  const canSupplier=can('lead.supplier.review');
  const source=S.leadSource||(!canPlatform?'SUPPLIER_H5':!canSupplier?'PLATFORM_MANUAL':'');
  const [platformData,supplierData]=await Promise.all([
    canPlatform&&source!=='SUPPLIER_H5'?api(`/v1.2/platform/leads${qs({page:S.platformLeadPage,page_size:20})}`):Promise.resolve({items:[]}),
    canSupplier&&source!=='PLATFORM_MANUAL'?api(`/v1.2/admin/supplier-leads${qs({page:S.supplierLeadPage,page_size:20})}`):Promise.resolve({items:[]}),
  ]);
  S.platformLeads=platformData.items||[];
  S.supplierLeads=supplierData.items||[];
  const platformRows=S.platformLeads.map(lead=>{
    const actions=[`<button class="ops-btn" data-platform-detail="${esc(lead.id)}">详情</button>`];
    if(!readOnly&&lead.status==='DRAFT'){
      actions.push(`<button class="ops-btn" data-platform-edit="${esc(lead.id)}">编辑</button>`);
      actions.push(`<button class="ops-btn primary" data-platform-submit="${esc(lead.id)}">资料完整，进入派发池</button>`);
      actions.push(`<button class="ops-btn" data-platform-pre-dispatch="${esc(lead.id)}">信息不全并派发电销</button>`);
    }
    return `<tr><td><b>${esc(lead.customer_name)}</b><br>${esc(lead.phone_masked||'--')}</td><td>${badge(lead.source_kind)}</td><td>${esc(lead.city||'--')} ${esc(lead.district||'')}</td><td>${badge(lead.status)} ${badge(lead.review_status)}</td><td>${fmt(lead.submitted_at||lead.created_at)}</td><td>${actions.join(' ')}</td></tr>`;
  });
  const supplierRows=S.supplierLeads.map(lead=>{
    const pending=lead.review_status==='PENDING';
    const actions=[`<button class="ops-btn" data-supplier-detail="${esc(lead.id)}">详情</button>`];
    if(!readOnly&&pending){
      actions.push(`<button class="ops-btn primary" data-review-qualified="${esc(lead.id)}">确认合格并派发电销</button>`);
      actions.push(`<button class="ops-btn" data-review-info="${esc(lead.id)}">信息不全并派发电销</button>`);
      actions.push(`<button class="ops-btn" data-review="${esc(lead.id)}:DUPLICATE">标记重复</button>`);
      actions.push(`<button class="ops-btn danger" data-review="${esc(lead.id)}:INVALID">明确无效</button>`);
    }
    return `<tr><td><b>${esc(lead.customer_name)}</b><br>${esc(lead.phone_masked||'--')}</td><td>${badge(lead.source_kind)}</td><td>${esc(lead.city||'--')} ${esc(lead.district||'')}</td><td>${badge(lead.status)} ${badge(lead.review_status)}</td><td>${fmt(lead.submitted_at)}</td><td>${actions.join(' ')}</td></tr>`;
  });
  const sourceOptions=[['','全部来源'],['PLATFORM_MANUAL','平台录入'],['SUPPLIER_H5','加盟商提交']].filter(([value])=>!value||(value==='PLATFORM_MANUAL'?canPlatform:canSupplier));
  const platformQueue=canPlatform&&source!=='SUPPLIER_H5'?`<section class="ops-card"><div class="ops-card-head"><div><h2>平台录入队列</h2><p>${readOnly?'只读查看平台客资的来源、状态和全流程记录。':'由运营补充资料、确认入池或指定电销核验。'}</p></div></div>${table(['客户','来源','所在地','状态','提交时间','操作'],platformRows)}${leadQueuePager(platformData,'platform-lead', 'platformLeadPage')}</section>`:'';
  const supplierQueue=canSupplier&&source!=='PLATFORM_MANUAL'?`<section class="ops-card"><div class="ops-card-head"><div><h2>加盟商客资队列</h2><p>${readOnly?'只读查看加盟商提交客资的审核与流转情况。':'仅加盟商来源可退回加盟商补正。'}</p></div></div>${table(['客户','来源','所在地','状态','提交时间','操作'],supplierRows)}${leadQueuePager(supplierData,'supplier-lead','supplierLeadPage')}</section>`:'';
  shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>${readOnly?'客资总览':'客资录入与初审'}</h2><p>${readOnly?'平台管理员可查看客资全量状态与处理详情，不在此创建或处置日常客资。':'平台来源由运营补充资料；加盟商来源才可退回加盟商补正。信息不足时必须派发给指定电销人员，电销不能自行领取核验任务。'}</p></div><div class="ops-actions"><select class="ops-input" id="lead-source-filter">${sourceOptions.map(([value,text])=>`<option value="${value}" ${source===value?'selected':''}>${text}</option>`).join('')}</select>${canPlatform&&!readOnly?'<button class="ops-btn primary" id="new-platform-lead">新建平台客资</button>':''}</div></div></section>${platformQueue}${supplierQueue}`);
  document.querySelector('#lead-source-filter').onchange=event=>setLeadSource(event.target.value);
  if(canPlatform&&source!=='SUPPLIER_H5')bindLeadQueuePager(platformData,'platform-lead','platformLeadPage');
  if(canSupplier&&source!=='PLATFORM_MANUAL')bindLeadQueuePager(supplierData,'supplier-lead','supplierLeadPage');
  document.querySelector('#new-platform-lead')?.addEventListener('click',()=>openPlatformLeadForm(null));
  document.querySelectorAll('[data-platform-detail]').forEach(button=>button.onclick=()=>platformDetail(button.dataset.platformDetail));
  document.querySelectorAll('[data-platform-edit]').forEach(button=>button.onclick=()=>openPlatformLeadForm(S.platformLeads.find(lead=>lead.id===button.dataset.platformEdit)));
  document.querySelectorAll('[data-platform-submit]').forEach(button=>button.onclick=()=>submitPlatformLead(button.dataset.platformSubmit));
  document.querySelectorAll('[data-platform-pre-dispatch]').forEach(button=>button.onclick=()=>assignPlatformPreDispatch(button.dataset.platformPreDispatch));
  document.querySelectorAll('[data-supplier-detail]').forEach(button=>button.onclick=()=>reviewDetail(button.dataset.supplierDetail));
  document.querySelectorAll('[data-review]').forEach(button=>button.onclick=()=>{
    const [id,decision]=button.dataset.review.split(':');
    reviewAction(id,decision);
  });
  document.querySelectorAll('[data-review-info]').forEach(button=>button.onclick=()=>assignInitialPreDispatch(button.dataset.reviewInfo,'INFO_INCOMPLETE'));
  document.querySelectorAll('[data-review-qualified]').forEach(button=>button.onclick=()=>assignInitialPreDispatch(button.dataset.reviewQualified,'QUALIFIED'));
  if(S.id){
    const id=S.id;
    S.id='';
    await openLeadDetail(id);
  }
}
function leadQueuePager(data,prefix,pageKey){const pages=Math.max(1,Math.ceil((data.total||0)/(data.page_size||20)));return `<div class="ops-pager"><button class="ops-btn" id="${prefix}-prev" ${S[pageKey]<=1?'disabled':''}>上一页</button><span>${S[pageKey]}/${pages}，共 ${data.total||0} 条</span><button class="ops-btn" id="${prefix}-next" ${S[pageKey]>=pages?'disabled':''}>下一页</button></div>`}
function bindLeadQueuePager(data,prefix,pageKey){const pages=Math.max(1,Math.ceil((data.total||0)/(data.page_size||20)));document.querySelector(`#${prefix}-prev`).onclick=()=>{S[pageKey]=Math.max(1,S[pageKey]-1);render()};document.querySelector(`#${prefix}-next`).onclick=()=>{S[pageKey]=Math.min(pages,S[pageKey]+1);render()}}
function setLeadSource(source){const url=new URL(location.href);source?url.searchParams.set('source',source):url.searchParams.delete('source');history.pushState(null,'',url);S.leadSource=source;S.platformLeadPage=1;S.supplierLeadPage=1;render()}
function leadDetailBody(x){return `<div class="ops-detail-grid">${[['客资编号',recordCode(x.id,'KZ')],['客资来源',label(x.source_kind)],['客户',x.customer_name],['手机号',x.phone_masked],['处理状态',label(x.status)],['初审结果',label(x.review_status)],['重复检查',label(x.duplicate_status)],['所在地',`${x.city||''} ${x.district||''}`]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>客户需求</h3><p class="ops-muted">${esc(x.need_summary||'暂无说明')}</p></section><button class="ops-btn" id="trace">查看处理详情</button>`}
function showLeadDetail(title,x){modal(title,leadDetailBody(x),()=>document.querySelector('#trace').onclick=()=>{closeModal();go('trace',x.id)})}
async function reviewDetail(id){const x=await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(id)}`);showLeadDetail('加盟商客资初审详情',x)}
async function platformDetail(id){const x=await api(`/v1.2/platform/leads/${encodeURIComponent(id)}`);showLeadDetail('平台客资详情',x)}
async function openLeadDetail(id){
  if(S.leadSource==='PLATFORM_MANUAL'){await platformDetail(id);return}
  if(S.leadSource==='SUPPLIER_H5'){await reviewDetail(id);return}
  try{await platformDetail(id)}catch{await reviewDetail(id)}
}
async function platformCities(){if(!S.platformCities){const tree=await api('/master-data/region-tree');S.platformCities=(tree.provinces||[]).flatMap(province=>(province.cities||[]).map(city=>({...city,province_code:province.code,province_name:province.name,option_name:`${province.name} · ${city.name}`})));}return S.platformCities}
async function platformDistricts(cityCode){const cities=await platformCities();S.platformDistricts=cities.find(city=>city.code===cityCode)?.districts||[];return S.platformDistricts}
const platformOptionName=item=>item.option_name||item.name;
function platformSelectOptions(items,currentCode,currentName,emptyLabel){const options=[...items];if(currentName&&!options.some(item=>item.name===currentName))options.unshift({code:currentCode||'',name:currentName});return `<option value="">${emptyLabel}</option>${options.map(item=>`<option value="${esc(item.code)}" ${item.code===currentCode||item.name===currentName?'selected':''}>${esc(platformOptionName(item))}</option>`).join('')}`}
function replacePlatformSelectOptions(select,items,currentCode,currentName,emptyLabel){const entries=[...items];if(currentName&&!entries.some(item=>item.name===currentName))entries.unshift({code:currentCode||'',name:currentName});const option=(code,name,selected=false)=>{const node=document.createElement('option');node.value=code;node.textContent=name;node.selected=selected;return node};const options=[option('',emptyLabel),...entries.map(item=>option(item.code,platformOptionName(item),item.code===currentCode||item.name===currentName))];select.replaceChildren(...options)}
function budgetToWan(value){if(value==null||value==='')return '';const amount=Number(value);return Number.isFinite(amount)?String(Number((amount/10000).toFixed(4))):''}
function budgetFromWan(selector){const raw=document.querySelector(selector).value.trim();if(raw==='')return null;const amount=Number(raw);return Number.isFinite(amount)?Math.round(amount*10000):NaN}
async function openPlatformLeadForm(item){
  const cities=await platformCities();
  const currentCity=cities.find(city=>city.name===item?.city)||null;
  const districts=await platformDistricts(currentCity?.code||'');
  const currentDistrict=districts.find(district=>district.name===item?.district)||null;
  const sourceOptions=[['MANUAL','人工录入'],['DOUYIN','抖音/信息流'],['WECHAT_VIDEO','视频号'],['XIAOHONGSHU','小红书']];
  const categoryOptions=[['OLD_RENOVATION','旧房改造'],['SELF_BUILD','农村自建房'],['INTERIOR','室内装修']];
  modal(item?'编辑平台客资':'新建平台客资',`<form class="ops-form" id="platform-lead-form"><div class="ops-notice">所在地可从全国城市中选择；保存草稿后，可选择“资料完整，进入派发池”或“信息不全并派发电销”。平台来源不会退回加盟商。</div><div class="ops-field"><label>客户姓名</label><input class="ops-input" id="platform-lead-name" value="${esc(item?.customer_name==='未填写'?'':item?.customer_name||'')}"></div><div class="ops-field"><label>联系电话</label><input class="ops-input" id="platform-lead-phone" inputmode="tel" value="${esc(item?.phone||'')}"></div><div class="ops-field"><label>所在地城市</label><select class="ops-input" id="platform-lead-city">${platformSelectOptions(cities,currentCity?.code||'',item?.city||'','请选择全国城市')}</select></div><div class="ops-field"><label>所在地区县</label><select class="ops-input" id="platform-lead-district">${platformSelectOptions(districts,currentDistrict?.code||'',item?.district||'','全市范围')}</select></div><div class="ops-field"><label>来源渠道</label><select class="ops-input" id="platform-lead-source">${sourceOptions.map(([code,name])=>`<option value="${code}" ${item?.source_channel===code?'selected':''}>${name}</option>`).join('')}</select></div><div class="ops-field"><label>咨询类别</label><select class="ops-input" id="platform-lead-category">${categoryOptions.map(([code,name])=>`<option value="${code}" ${item?.category_code===code?'selected':''}>${name}</option>`).join('')}</select></div><div class="ops-field"><label>预算下限（万元）</label><input class="ops-input" id="platform-lead-budget-min" type="number" min="0" step="0.1" inputmode="decimal" value="${esc(budgetToWan(item?.budget_min))}"></div><div class="ops-field"><label>预算上限（万元）</label><input class="ops-input" id="platform-lead-budget-max" type="number" min="0" step="0.1" inputmode="decimal" value="${esc(budgetToWan(item?.budget_max))}"></div><div class="ops-field"><label>客户需求</label><textarea class="ops-textarea" id="platform-lead-need">${esc(item?.need_summary||'')}</textarea></div><label class="ops-field"><input id="platform-lead-consent" type="checkbox" ${item?.consent_confirmed?'checked':''}> 已获得客户信息授权</label><div class="ops-actions"><button class="ops-btn" type="button" id="platform-lead-cancel">取消</button><button class="ops-btn primary" type="submit">保存草稿</button></div></form>`,()=>{
    const form=document.querySelector('#platform-lead-form');
    document.querySelector('#platform-lead-cancel').onclick=closeModal;
    document.querySelector('#platform-lead-city').onchange=async event=>{const next=await platformDistricts(event.target.value);replacePlatformSelectOptions(document.querySelector('#platform-lead-district'),next,'','','全市范围')};
    form.onsubmit=event=>{event.preventDefault();savePlatformLead(item?.id||null)};
  });
}
async function savePlatformLead(id){
  const citySelect=document.querySelector('#platform-lead-city');
  const districtSelect=document.querySelector('#platform-lead-district');
  const cities=await platformCities();
  const city=cities.find(item=>item.code===citySelect.value);
  const districts=await platformDistricts(citySelect.value);
  const district=districts.find(item=>item.code===districtSelect.value);
  const budget_min=budgetFromWan('#platform-lead-budget-min'),budget_max=budgetFromWan('#platform-lead-budget-max');
  if(Number.isNaN(budget_min)||Number.isNaN(budget_max)||budget_min!=null&&budget_min<0||budget_max!=null&&budget_max<0){toast('请填写有效的预算金额（万元）',true);return}
  if(budget_min!=null&&budget_max!=null&&budget_min>budget_max){toast('预算上限不能低于预算下限',true);return}
  const payload={customer_name:document.querySelector('#platform-lead-name').value.trim()||null,phone:document.querySelector('#platform-lead-phone').value.trim()||null,city:city?.name||null,district:district?.name||null,region_code:district?.code||city?.code||null,source_channel:document.querySelector('#platform-lead-source').value,category_code:document.querySelector('#platform-lead-category').value,need_summary:document.querySelector('#platform-lead-need').value.trim()||null,budget_min,budget_max,consent_confirmed:document.querySelector('#platform-lead-consent').checked};
  try{await api(id?`/v1.2/platform/leads/${encodeURIComponent(id)}`:'/v1.2/platform/leads',{method:id?'PATCH':'POST',body:JSON.stringify(payload)});closeModal();toast('平台客资草稿已保存');await review()}catch(error){toast(error.message,true)}
}
async function submitPlatformLead(id){try{await api(`/v1.2/platform/leads/${encodeURIComponent(id)}/submit`,{method:'POST'});toast('资料完整，已进入待派发池');await review()}catch(error){toast(error.message,true)}}
async function assignPlatformPreDispatch(leadId){
  const lead=S.platformLeads.find(item=>item.id===leadId);
  if(!lead?.phone_masked){toast('请先补充客户联系电话，再派发电话核验',true);openPlatformLeadForm(lead);return}
  try{const users=await loadTelesalesUsers();const options=users.map(user=>`<option value="${esc(user.id)}">${esc(user.display_name||user.username)}</option>`).join('');modal('信息不全并派发电销',users.length?`<form class="ops-form" id="platform-pre-dispatch-form"><div class="ops-notice">此操作会将平台草稿转入电话核验，后续补充由运营处理，不会退回加盟商。</div><div class="ops-field"><label>电销人员 *</label><select class="ops-input" id="platform-pre-assignee">${options}</select></div><div class="ops-field"><label>核验重点 *</label><textarea class="ops-textarea" id="platform-pre-reason" placeholder="例如：补充联系方式、客户授权和具体需求"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="platform-pre-cancel">取消</button><button class="ops-btn primary" type="submit">确认派发</button></div></form>`:'<div class="ops-empty">暂无可分配的电销人员</div>',()=>{const form=document.querySelector('#platform-pre-dispatch-form');if(!form)return;document.querySelector('#platform-pre-cancel').onclick=closeModal;form.onsubmit=async event=>{event.preventDefault();const reason=document.querySelector('#platform-pre-reason').value.trim();if(reason.length<2){toast('请至少填写 2 个字的核验重点',true);return}try{await api(`/v1.2/admin/leads/${encodeURIComponent(leadId)}/pre-dispatch-verification`,{method:'POST',body:JSON.stringify({assignee_user_id:document.querySelector('#platform-pre-assignee').value,reason})});closeModal();toast('已派发平台客资电话核验');await review()}catch(error){toast(error.message,true)}}})}catch(error){toast(error.message,true)}
}
function reviewAction(id,decision){const copy={QUALIFIED:['确认客资合格','资料完整且不需要电话补充，将进入待派发池。',false,false],DUPLICATE:['标记重复客资','请写明重复判断依据，客资将进入重复核查。',true,false],INVALID:['确认客资无效','请写明无效原因，加盟商可根据说明补正后重新提交。',true,true]}[decision];actionForm({title:copy[0],message:copy[1],labelText:'初审说明',required:copy[2],minLength:2,submitLabel:'确认提交',danger:copy[3]},async note=>{await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(id)}/review`,{method:'POST',body:JSON.stringify({decision,note:note||null})});toast('初审结果已提交');await review()})}
async function assignInitialPreDispatch(leadId,decision='INFO_INCOMPLETE'){
  try{
    const users=await loadTelesalesUsers();
    const options=users.map(user=>`<option value="${esc(user.id)}">${esc(user.display_name||user.username)}${user.username?` · ${esc(user.username)}`:''}</option>`).join('');
    const qualified=decision==='QUALIFIED';
    modal(qualified?'确认合格并派发电销':'信息不全并派发电销',users.length?`<form class="ops-form" id="initial-pre-dispatch-form"><div class="ops-notice">加盟商提交的客资无论初审是否完整，均须先由电销核实，核实通过后才会进入派发池。</div><div class="ops-field"><label for="initial-pre-assignee">电销人员 *</label><select class="ops-input" id="initial-pre-assignee">${options}</select></div><div class="ops-field"><label for="initial-pre-note">初审说明 *</label><textarea class="ops-textarea" id="initial-pre-note" placeholder="${qualified?'记录初审通过依据':'说明哪些资料不足'}"></textarea></div><div class="ops-field"><label for="initial-pre-reason">核验重点 *</label><textarea class="ops-textarea" id="initial-pre-reason" placeholder="例如：确认客户意向、预算和可联系时间"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="initial-pre-cancel">取消</button><button class="ops-btn primary" id="initial-pre-submit">确认派发</button></div></form>`:'<div class="ops-empty">暂无可分配的电销人员</div>',()=>{
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
          await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(leadId)}/review`,{method:'POST',body:JSON.stringify({decision,note,assignee_user_id:document.querySelector('#initial-pre-assignee').value,pre_dispatch_reason:reason})});
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
      ?`<button class="ops-btn primary" data-pre-disposition="${esc(task.lead_id)}:${esc(lead.source_kind||'')}">运营处置</button>`
      :`<button class="ops-btn" data-pre-assign="${esc(task.lead_id)}">${task.assignee_user_id?'改派':'派发'}</button>`;
    return `<tr><td><b>${esc(lead.customer_name||'待核验客户')}</b><br><small>${esc(lead.phone_masked||'--')}</small></td><td>${badge(lead.source_kind)}</td><td>${verificationTaskBadge(task)}</td><td>${esc(telesalesName(task.assignee_user_id))}</td><td>${esc(label(task.conclusion))}</td><td>${esc(nextStep)}</td><td>${fmt(task.due_at)}</td><td>${action}</td></tr>`;
  });
  shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>前置电销核验</h2><p>运营在此分配或改派；平台来源补充资料由运营处理，加盟商来源才可退回加盟商补正。超时任务需改派后重新核验。</p></div></div>${table(['客户','来源','任务状态','电销人员','事实结论','下一步','核验截止','操作'],rows)}${pager(data)}</section>`);
  bindPager(data,telesales);
  document.querySelectorAll('[data-pre-assign]').forEach(button=>button.onclick=()=>assignPreDispatch(button.dataset.preAssign));
  document.querySelectorAll('[data-pre-disposition]').forEach(button=>button.onclick=()=>{const [leadId,sourceKind]=button.dataset.preDisposition.split(':');disposePreDispatch(leadId,sourceKind)});
  if(S.id){const taskId=S.id;S.id='';await openPreDispatchTask(taskId)}
}
async function openPreDispatchTask(taskId){
  const task=await api(`/v1.2/pre-dispatch-verifications/tasks/${encodeURIComponent(taskId)}`);
  if(task.status!=='SUBMITTED'){toast('该电销核验任务当前无需运营处置',true);return}
  disposePreDispatch(task.lead_id,task.lead?.source_kind||'');
}
function disposePreDispatch(leadId,sourceKind=''){
  const platform=sourceKind==='PLATFORM_MANUAL';
  modal('运营处置电销结论',`<form class="ops-form" id="pre-disposition-form"><div class="ops-notice">电销只提供核验事实；${platform?'平台来源由运营补充资料，不会退回加盟商。':'加盟商来源可按运营说明退回补正。'}</div><div class="ops-field"><label for="pre-disposition-decision">后续处理 *</label><select class="ops-input" id="pre-disposition-decision"><option value="APPROVE_POOL">确认合格，进入派发池</option><option value="RETURN_REWORK">${platform?'资料待补，平台补充资料后再处理':'资料待补，退回加盟商补正'}</option><option value="DUPLICATE">标记为重复客资</option><option value="CLOSE">关闭该客资</option></select></div><div class="ops-field"><label for="pre-disposition-note">运营处理说明 *</label><textarea class="ops-textarea" id="pre-disposition-note" placeholder="写明结合电销结论作出的处理判断"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="pre-disposition-cancel">取消</button><button class="ops-btn primary" id="pre-disposition-submit">确认处置</button></div></form>`,()=>{
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
const INTERNAL_ROLE_OPTIONS=[['SUPER_ADMIN','超级管理员'],['OPERATION','运营管理员'],['TELESALES','电销人员']];
const INTERNAL_ROLE_LABEL=Object.fromEntries(INTERNAL_ROLE_OPTIONS);
const calendarMonthValue=moment=>{const parts=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit'}).formatToParts(moment).filter(part=>part.type!=='literal').map(part=>[part.type,part.value]));return `${parts.year}-${parts.month}`};
const calendarRange=value=>{const [year,month]=value.split('-').map(Number),daysInMonth=new Date(Date.UTC(year,month,0)).getUTCDate();return {year,month,daysInMonth,start:`${value}-01`,end:`${value}-${String(daysInMonth).padStart(2,'0')}`}};
const shiftCalendarMonth=(value,offset)=>{const [year,month]=value.split('-').map(Number),absolute=year*12+month-1+offset;return `${Math.floor(absolute/12)}-${String(absolute%12+1).padStart(2,'0')}`};
const calendarUpdatedBy=item=>item.updated_by_name||(item.updated_by?recordCode(item.updated_by,'账号'):'系统默认规则');
const calendarUpdatedAt=item=>item.updated_at?new Date(item.updated_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'--';
const calendarDayBadge=item=>`<span class="ops-status ${item.is_workday?'ok':''}">${item.is_workday?'工作日':'休息日'}</span>`;
function calendarDayModal(dayValue,item={},lockedDate=false){
  const day=dayValue||`${S.calendarMonth}-01`,isWorkday=typeof item.is_workday==='boolean'?item.is_workday:true;
  modal(lockedDate?'编辑工作日历日期':'单日设定',`<form class="ops-form" id="calendar-form"><div class="ops-field"><label for="calendar-day">日期 *</label><input class="ops-input" id="calendar-day" type="date" value="${esc(day)}" ${lockedDate?'readonly':''}></div><div class="ops-field"><label for="calendar-is-workday">当天安排 *</label><select class="ops-input" id="calendar-is-workday"><option value="true" ${isWorkday?'selected':''}>工作日</option><option value="false" ${isWorkday?'':'selected'}>休息日</option></select></div><div class="ops-field"><label for="calendar-holiday-name">节日或说明</label><input class="ops-input" id="calendar-holiday-name" maxlength="128" value="${esc(item.holiday_name||'')}" placeholder="例如：国庆节或调休工作日"></div><div class="ops-notice">只影响保存后新领取或历史缺失字段补算；已固化的历史截止时间不回算。</div><div class="ops-actions"><button type="button" class="ops-btn" id="calendar-cancel">取消</button><button class="ops-btn primary" id="calendar-submit">保存</button></div></form>`,()=>{
    const form=document.querySelector('#calendar-form'),submit=document.querySelector('#calendar-submit');
    document.querySelector('#calendar-cancel').onclick=closeModal;
    form.onsubmit=async event=>{event.preventDefault();const selectedDay=document.querySelector('#calendar-day').value.trim();if(!selectedDay){toast('请选择日期',true);return}submit.disabled=true;try{const result=await api(`/admin/v1.2/calendar-days/${encodeURIComponent(selectedDay)}`,{method:'PUT',body:JSON.stringify({is_workday:document.querySelector('#calendar-is-workday').value==='true',holiday_name:document.querySelector('#calendar-holiday-name').value.trim()||null})});toast(result.changed?'工作日历已保存':'配置无变化，未重复写入审计');closeModal();await calendar()}catch(error){submit.disabled=false;toast(error.message,true)}};
  });
}
function calendarDayDetail(item){
  modal('工作日历详情',`<div class="ops-detail-grid">${[['日期',item.day],['当天安排',item.is_workday?'工作日':'休息日'],['设置方式',item.is_override?'单日调整':'系统默认'],['节日或说明',item.holiday_name||'--'],['变更人',calendarUpdatedBy(item)],['变更时间（中国时区）',calendarUpdatedAt(item)]].map(([name,value])=>`<div class="ops-detail"><small>${esc(name)}</small><b>${esc(value)}</b></div>`).join('')}</div><div class="ops-notice">只影响保存后新领取或历史缺失字段补算；已固化的历史截止时间不回算。</div><div class="ops-actions"><button class="ops-btn primary" id="calendar-edit">编辑当天</button></div>`,()=>document.querySelector('#calendar-edit').onclick=()=>calendarDayModal(item.day,item,true));
}
async function calendar(){
  S.calendarMonth=S.calendarMonth||calendarMonthValue(new Date());
  const range=calendarRange(S.calendarMonth),items=await api(`/admin/v1.2/calendar-days?start=${range.start}&end=${range.end}`);
  if(items.length!==range.daysInMonth)throw new Error('工作日历返回的有效日期不完整');
  const overrides=items.filter(item=>item.is_override),leadingDays=(new Date(Date.UTC(range.year,range.month-1,1)).getUTCDay()+6)%7;
  const cells=[...Array(leadingDays)].map(()=>'<div class="ops-calendar-blank" aria-hidden="true"></div>');
  cells.push(...items.map(item=>`<button class="ops-calendar-day ${item.is_workday?'':'rest'}" type="button" data-calendar-day="${esc(item.day)}"><b>${Number(item.day.slice(-2))}</b><span>${esc(item.is_workday?'工作日':'休息日')}</span><small>${esc(item.holiday_name||(item.is_override?'单日调整':'默认规则'))}</small></button>`));
  const rows=overrides.map(item=>`<tr><td><b>${esc(item.day)}</b></td><td>${calendarDayBadge(item)}</td><td>${esc(item.holiday_name||'--')}</td><td>${esc(calendarUpdatedBy(item))}<br><small>${esc(calendarUpdatedAt(item))}</small></td><td><button class="ops-btn" data-calendar-day="${esc(item.day)}">查看</button></td></tr>`);
  shell(`<div class="ops-page-actions"><button class="ops-btn" data-view="settings">返回设置</button><div class="ops-calendar-controls"><button class="ops-btn" id="calendar-prev">上月</button><input class="ops-input" id="calendar-month" type="month" value="${esc(S.calendarMonth)}"><button class="ops-btn" id="calendar-next">下月</button><button class="ops-btn primary" id="calendar-new">单日设定</button></div></div><section class="ops-card"><div class="ops-card-head"><div><h2>${esc(S.calendarMonth)} 工作日历</h2><p>默认按周一到周五计算工作日，法定节假日和调休只维护单日例外。</p></div></div><div class="ops-notice">只影响保存后新领取或历史缺失字段补算；已固化的历史截止时间不回算。</div><div class="ops-calendar-week">${['一','二','三','四','五','六','日'].map(day=>`<span>${day}</span>`).join('')}</div><div class="ops-calendar-grid">${cells.join('')}</div></section><section class="ops-card"><div class="ops-card-head"><div><h2>单日例外</h2><p>本月共 ${overrides.length} 项显式调整。</p></div></div>${table(['日期','状态','节日或说明','变更人/时间','操作'],rows)}</section>`);
  const byDay=Object.fromEntries(items.map(item=>[item.day,item]));
  document.querySelector('#calendar-month').onchange=event=>{S.calendarMonth=event.target.value;calendar()};
  document.querySelector('#calendar-prev').onclick=()=>{S.calendarMonth=shiftCalendarMonth(S.calendarMonth,-1);calendar()};
  document.querySelector('#calendar-next').onclick=()=>{S.calendarMonth=shiftCalendarMonth(S.calendarMonth,1);calendar()};
  document.querySelector('#calendar-new').onclick=()=>calendarDayModal(range.start,byDay[range.start]);
  document.querySelectorAll('[data-calendar-day]').forEach(button=>button.onclick=()=>calendarDayDetail(byDay[button.dataset.calendarDay]));
}
const internalUserRoles=user=>(user.roles||user.role_codes||[]).filter(role=>INTERNAL_ROLE_LABEL[role]);
const internalRoleOptions=(name,current='OPERATION')=>INTERNAL_ROLE_OPTIONS.map(([role,labelText])=>`<label class="ops-choice"><input type="radio" name="${esc(name)}" value="${role}" ${role===current?'checked':''}>${labelText}</label>`).join('');
const selectedInternalRole=name=>document.querySelector(`input[name="${name}"]:checked`)?.value||'';
async function runInternalUserAction(button,action,success){
  const original=button.textContent;button.disabled=true;button.textContent='处理中';
  try{await action();toast(success);closeModal();await internalUsers()}catch(error){toast(error.message,true)}finally{if(button.isConnected){button.disabled=false;button.textContent=original}}
}
function showInternalUserCredentials(user,onClose){
  const password=user.initial_password||'',username=user.username||'';
  if(!password){modal('内部账号已创建',`<div class="ops-notice">账号已创建，但初始密码未返回。请立即在账号列表中重置密码后再交付账号本人。</div><div class="ops-detail"><small>登录账号</small><b>${esc(username)}</b></div>`,()=>{});return false}
  const credentials=`登录账号：${username}\n初始密码：${password}`;
  modal('请安全交付初始密码',`<div class="ops-notice">初始密码仅在当前窗口展示一次，请立即复制并通过安全渠道交付账号本人。</div><div class="ops-detail-grid"><div class="ops-detail"><small>登录账号</small><b>${esc(username)}</b></div><div class="ops-detail"><small>初始密码</small><b id="internal-user-password">${esc(password)}</b></div></div><div class="ops-actions"><button class="ops-btn primary" id="copy-internal-user-password">复制初始密码</button><button class="ops-btn" id="copy-internal-user-credentials">复制账号与密码</button><button class="ops-btn" id="internal-user-credentials-close">已保存</button></div>`,()=>{
    const copy=value=>navigator.clipboard.writeText(value).then(()=>toast('已复制')).catch(()=>toast('浏览器不支持自动复制，请手动复制',true));
    document.querySelector('#copy-internal-user-password').onclick=()=>copy(password);
    document.querySelector('#copy-internal-user-credentials').onclick=()=>copy(credentials);
    document.querySelector('#internal-user-credentials-close').onclick=()=>{closeModal();onClose?.()};
  });
  return true;
}
function internalUserModal(){
  modal('新建内部账号',`<form class="ops-form" id="internal-user-form"><div class="ops-field"><label for="internal-user-name">姓名 *</label><input class="ops-input" id="internal-user-name" maxlength="64" autocomplete="name"></div><div class="ops-field"><label for="internal-user-username">登录账号 *</label><input class="ops-input" id="internal-user-username" maxlength="64" autocomplete="username"></div><div class="ops-notice">无需填写密码，系统会自动生成可复制的 8 位以上初始密码。</div><div class="ops-field"><label>角色 *</label><div class="ops-choice-list">${internalRoleOptions('internal-role')}</div><small class="ops-muted">单选，仅限平台内部角色。</small></div><div class="ops-actions"><button type="button" class="ops-btn" id="internal-user-cancel">取消</button><button class="ops-btn primary" id="internal-user-submit">创建</button></div></form>`,()=>{
    const form=document.querySelector('#internal-user-form'),submit=document.querySelector('#internal-user-submit');
    document.querySelector('#internal-user-cancel').onclick=closeModal;
    form.onsubmit=async event=>{event.preventDefault();const display_name=document.querySelector('#internal-user-name').value.trim(),username=document.querySelector('#internal-user-username').value.trim(),role=selectedInternalRole('internal-role');if(!display_name){toast('请输入姓名',true);return}if(username.length<2){toast('登录账号至少输入 2 个字符',true);return}if(!role){toast('请选择一个角色',true);return}submit.disabled=true;try{const created=await api('/users',{method:'POST',body:JSON.stringify({display_name,username,role_codes:[role]})});const passwordReady=showInternalUserCredentials(created);toast(passwordReady?'账号已创建，请复制初始密码':'账号已创建，但需要立即重置密码',!passwordReady);try{await internalUsers()}catch(refreshError){toast(`账号已创建，但账号列表刷新失败：${refreshError.message}`,true)}}catch(error){submit.disabled=false;toast(error.message,true)}};
  });
}
function internalRoleModal(user){
  const current=internalUserRoles(user)[0]||'OPERATION';
  modal('编辑内部账号角色',`<form class="ops-form" id="internal-role-form"><div class="ops-notice">${esc(user.display_name)} · ${esc(user.username||'--')}。一个账号只能有一个角色，保存后该账号现有会话立即失效。</div><div class="ops-field"><label>角色 *</label><div class="ops-choice-list">${internalRoleOptions('internal-role-edit',current)}</div></div><div class="ops-actions"><button type="button" class="ops-btn" id="internal-role-cancel">取消</button><button class="ops-btn primary" id="internal-role-submit">保存角色</button></div></form>`,()=>{
    const form=document.querySelector('#internal-role-form'),submit=document.querySelector('#internal-role-submit');document.querySelector('#internal-role-cancel').onclick=closeModal;
    form.onsubmit=event=>{event.preventDefault();const role=selectedInternalRole('internal-role-edit');runInternalUserAction(submit,()=>api(`/users/${encodeURIComponent(user.id)}/roles`,{method:'PUT',body:JSON.stringify({role_codes:[role]})}),'角色已更新')};
  });
}
function resetInternalUserPassword(user){
  actionForm({title:'重置内部账号密码',message:'保存后该账号现有会话立即失效。',labelText:'新密码',required:true,minLength:8,submitLabel:'重置密码',danger:true,validate:value=>value.length>128?'密码需为 8-128 位':null},async new_password=>{if(new_password.length<8)throw new Error('密码需为 8-128 位');await api(`/users/${encodeURIComponent(user.id)}/reset-password`,{method:'POST',body:JSON.stringify({new_password})});toast('密码已重置');await internalUsers()});
}
async function internalUsers(){
  const data=await api('/users'),users=data.filter(user=>!user.company_id&&internalUserRoles(user).length);
  const rows=users.map(user=>{const active=user.status==='ACTIVE';return `<tr><td><b>${esc(user.display_name)}</b></td><td>${esc(user.username||'--')}</td><td>${esc(INTERNAL_ROLE_LABEL[internalUserRoles(user)[0]]||'--')}</td><td>${badge(user.status)}</td><td><button class="ops-btn" data-internal-role="${esc(user.id)}">编辑角色</button> <button class="ops-btn" data-internal-reset="${esc(user.id)}">重置密码</button> <button class="ops-btn ${active?'danger':'primary'}" data-internal-status="${esc(user.id)}:${active?'disable':'enable'}">${active?'停用':'启用'}</button></td></tr>`});
  shell(`<div class="ops-page-actions"><button class="ops-btn" data-view="settings">返回设置</button><button class="ops-btn primary" id="new-internal-user">新建内部账号</button></div><section class="ops-card"><div class="ops-card-head"><div><h2>内部账号</h2><p>只管理平台内部账号；创建、改角色、启停和重置密码都会使相关会话失效。</p></div></div>${table(['姓名','登录账号','角色','状态','操作'],rows)}</section>`);
  const byId=Object.fromEntries(users.map(user=>[user.id,user]));
  document.querySelector('#new-internal-user').onclick=internalUserModal;
  document.querySelectorAll('[data-internal-role]').forEach(button=>button.onclick=()=>internalRoleModal(byId[button.dataset.internalRole]));
  document.querySelectorAll('[data-internal-reset]').forEach(button=>button.onclick=()=>resetInternalUserPassword(byId[button.dataset.internalReset]));
  document.querySelectorAll('[data-internal-status]').forEach(button=>button.onclick=()=>{const [userId,action]=button.dataset.internalStatus.split(':');const user=byId[userId],enabling=action==='enable';actionForm({title:enabling?'启用内部账号':'停用内部账号',message:enabling?'启用后该账号可重新登录。':'停用后该账号的全部会话会立即失效。',submitLabel:enabling?'确认启用':'确认停用',danger:!enabling},async()=>{await api(`/users/${encodeURIComponent(user.id)}/${enabling?'enable':'disable'}`,{method:'POST'});toast(enabling?'账号已启用':'账号已停用');await internalUsers()})});
}
async function settings(){
  shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>系统设置</h2><p>只保留系统治理必需的内部账号、工作日历和加盟商治理，不展示底层参数或旧版入口。</p></div></div><div class="ops-settings-grid"><button class="ops-setting-card" data-view="users"><i>${icon('users')}</i><b>内部账号</b><span>开通、角色调整、启停和密码重置</span></button><button class="ops-setting-card" data-view="calendar"><i>${icon('calendar')}</i><b>工作日历</b><span>维护法定节假日与调休单日例外</span></button><button class="ops-setting-card" data-view="companies"><i>${icon('building')}</i><b>加盟商治理</b><span>审核公司、能力区域和加盟商账号</span></button></div></section>`);
}
async function account(){
  const accountName=S.me?.username||'当前账号';
  const identity=ROLE_IDENTITY_LABEL[primaryRole()]||'平台人员';
  const tool=(view,iconName,title,description)=>`<button class="ops-account-tool" data-account-tool="${esc(view)}" type="button"><i>${icon(iconName)}</i><span><b>${esc(title)}</b><small>${esc(description)}</small></span><em>${icon('chevron-right')}</em></button>`;
  const tools=[];
  if(isSuperAdmin())tools.push(tool('settings','settings','系统设置','管理内部账号和工作日历'));
  if(canOpenView('returns'))tools.push(tool('returns','rotate-ccw','异常处理','处理退回申诉与电话核验任务'));
  if(canOpenView('audit'))tools.push(tool('audit','search','操作日志','查看业务处理记录与通知异常'));
  shell(`<section class="ops-account-page"><section class="ops-card ops-account-summary"><div class="ops-account-avatar">${icon('user')}</div><div><h2>${esc(accountName)}</h2><p>${esc(identity)} · ${esc(S.me?.company_name||'合家美宅平台')}</p></div></section><section class="ops-card"><div class="ops-card-head"><div><h3>安全与登录</h3><p>仅保留账号维护所需的操作。</p></div></div><div class="ops-account-security-list"><button class="ops-security-action" id="account-username" type="button"><i>${icon('user')}</i><span><b>修改登录账号</b><small>修改后使用新账号登录</small></span><em>${icon('chevron-right')}</em></button><button class="ops-security-action" id="account-password" type="button"><i>${icon('key-round')}</i><span><b>修改登录密码</b><small>保存后其他设备自动退出</small></span><em>${icon('chevron-right')}</em></button></div><button class="ops-btn danger ops-account-logout" id="account-logout" type="button">${icon('log-out')}退出当前账号</button></section>${tools.length?`<section class="ops-card ops-account-tools"><div class="ops-card-head"><div><h3>常用管理</h3><p>异常和日志从这里查看，避免占用业务导航。</p></div></div><div class="ops-account-tool-grid">${tools.join('')}</div></section>`:''}</section>`);
  document.querySelector('#account-username').onclick=changeOwnUsername;
  document.querySelector('#account-password').onclick=changeOwnPassword;
  document.querySelector('#account-logout').onclick=async()=>{await api('/auth/logout',{method:'POST'}).catch(()=>{});location.replace('/admin/')};
  document.querySelectorAll('[data-account-tool]').forEach(button=>button.onclick=()=>go(button.dataset.accountTool));
}
function changeOwnUsername(){
  const current=S.me?.username||'';
  modal('修改登录账号',`<form class="ops-form" id="own-username-form"><div class="ops-notice">修改后立即使用新登录账号；当前设备保持登录，原登录账号将不能再用于登录。</div><div class="ops-field"><label for="username-current-password">当前密码 *</label><input class="ops-input" id="username-current-password" type="password" autocomplete="current-password" minlength="8" maxlength="128" required></div><div class="ops-field"><label for="new-username">新登录账号 *</label><input class="ops-input" id="new-username" value="${esc(current)}" autocomplete="username" minlength="2" maxlength="64" required></div><div class="ops-actions"><button class="ops-btn" type="button" id="own-username-cancel">取消</button><button class="ops-btn primary" id="own-username-submit">保存登录账号</button></div></form>`,()=>{
    const form=document.querySelector('#own-username-form'),submit=document.querySelector('#own-username-submit');
    document.querySelector('#own-username-cancel').onclick=closeModal;
    form.onsubmit=async event=>{event.preventDefault();const current_password=document.querySelector('#username-current-password').value,username=document.querySelector('#new-username').value.trim();if(username.length<2){toast('登录账号至少 2 个字符',true);return}submit.disabled=true;try{await api('/auth/change-username',{method:'POST',body:JSON.stringify({current_password,username})});S.me=await api('/auth/me');toast('登录账号已更新');closeModal();await account()}catch(error){submit.disabled=false;toast(error.message,true)}};
  });
}
function changeOwnPassword(){
  modal('修改登录密码',`<form class="ops-form" id="own-password-form"><div class="ops-notice">新密码只要求 8 至 128 位，不要求字符组合。保存后，本设备会保持登录，其他设备会自动退出。</div><div class="ops-field"><label for="current-password">当前密码 *</label><input class="ops-input" id="current-password" type="password" autocomplete="current-password" minlength="8" maxlength="128" required></div><div class="ops-field"><label for="new-password">新密码 *</label><input class="ops-input" id="new-password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required></div><div class="ops-field"><label for="confirm-password">确认新密码 *</label><input class="ops-input" id="confirm-password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required></div><div class="ops-actions"><button class="ops-btn" type="button" id="own-password-cancel">取消</button><button class="ops-btn primary" id="own-password-submit">保存新密码</button></div></form>`,()=>{
    const form=document.querySelector('#own-password-form'),submit=document.querySelector('#own-password-submit');
    document.querySelector('#own-password-cancel').onclick=closeModal;
    form.onsubmit=async event=>{event.preventDefault();const current_password=document.querySelector('#current-password').value,new_password=document.querySelector('#new-password').value,confirm_password=document.querySelector('#confirm-password').value;if(new_password.length<8){toast('新密码至少 8 位',true);return}if(new_password!==confirm_password){toast('两次输入的新密码不一致',true);return}submit.disabled=true;try{await api('/auth/change-password',{method:'POST',body:JSON.stringify({current_password,new_password})});toast('密码已更新，其他设备已退出');closeModal();await account()}catch(error){submit.disabled=false;toast(error.message,true)}};
  });
}
async function companies(){
  const [companyPage,capabilities,areas]=await Promise.all([
    api(`/companies${qs({keyword:S.companyKeyword,status:S.companyLifecycleStatus,page:S.companyPage,page_size:20})}`),
    api(`/v1.2/admin/company-capabilities${qs({review_status:S.companyStatus,page:S.companyCapabilityPage,page_size:20})}`),
    api(`/v1.2/admin/service-areas${qs({review_status:S.companyStatus,page:S.companyAreaPage,page_size:20})}`),
  ]);
  const companyAssignmentSummary=summary=>{
    const byStatus=summary?.by_status||{};
    const statuses=Object.entries(byStatus).map(([status,count])=>`${label(status)} ${Number(count||0)} 条`).join('、');
    return `<small>共 ${Number(summary?.total||0)} 条</small><br><small>${esc(statuses||'暂无已派发客资')}</small>`;
  };
  const companyRows=(companyPage.items||[]).map(company=>`<tr><td><b>${esc(company.name)}</b><br><small>${esc(company.code)}</small></td><td>${badge(company.status)}</td><td>${companyAssignmentSummary(company.assignment_summary)}</td><td>${esc(company.owner_name||'--')}</td><td><button class="ops-btn" data-company-edit="${esc(company.id)}">编辑资料</button> <button class="ops-btn primary" data-company-accounts="${esc(company.id)}" data-company-name="${esc(company.name)}">账号与人员</button></td></tr>`);
  const capabilityRows=(capabilities.items||[]).map(item=>`<tr><td><b>${esc(item.company_name)}</b><br><small>${esc(recordCode(item.company_id,'加盟商'))}</small></td><td>${esc(CAPABILITY_LABEL[item.capability_code]||readableLabel(item.capability_code,'其他能力'))}</td><td>${badge(item.review_status)}<br><small>${item.active?'已启用':'未启用'}</small></td><td>${esc(cleanProfileNote(item.review_note)||'--')}</td><td>${fmt(item.reviewed_at)}</td><td>${capabilityReviewActions(item)} <button class="ops-btn" data-company-accounts="${esc(item.company_id)}" data-company-name="${esc(item.company_name)}">账号与人员</button></td></tr>`);
  const areaRows=(areas.items||[]).map(item=>{const removal=String(item.review_note||'').startsWith('[REMOVE_REQUEST]');return `<tr><td><b>${esc(item.company_name)}</b><br><small>${esc(recordCode(item.company_id,'加盟商'))}</small></td><td>${esc(item.region_name||recordCode(item.region_code,'区域'))}<br><small>${esc(item.is_primary_city?'主要城市':readableLabel(item.region_level,'服务区域'))}</small></td><td>${badge(item.review_status)}<br><small>${removal&&item.active?'待移除，当前仍生效':item.active?'已生效':'未生效'}</small></td><td>${esc(cleanProfileNote(item.review_note)||'--')}</td><td>${fmt(item.reviewed_at)}</td><td>${areaReviewActions(item)}</td></tr>`});
  shell(`<section class="ops-card company-review"><div class="ops-card-head"><div><h2>加盟商主体</h2><p>在这里新建独立加盟商主体，例如“北京合家美宅”；服务范围按省、市、区县登记，创建后立即开通接单资格并同步到加盟商 H5。</p></div><button class="ops-btn primary" id="new-franchise-company" type="button">新建加盟商</button></div><form class="ops-filter-row" id="company-filter-form"><input class="ops-input" id="company-keyword" value="${esc(S.companyKeyword)}" placeholder="搜索公司名称或编号"><select class="ops-input" id="company-lifecycle-status"><option value="" ${S.companyLifecycleStatus===''?'selected':''}>全部状态</option><option value="ACTIVE" ${S.companyLifecycleStatus==='ACTIVE'?'selected':''}>正常</option><option value="PENDING" ${S.companyLifecycleStatus==='PENDING'?'selected':''}>待审核</option><option value="DISABLED" ${S.companyLifecycleStatus==='DISABLED'?'selected':''}>已停用</option></select><button class="ops-btn primary" type="submit">查询</button><button class="ops-btn" id="company-filter-reset" type="button">重置</button></form>${table(['加盟商','公司状态','公司客资状态','负责人','操作'],companyRows)}${companyQueuePager(companyPage,'company-list',S.companyPage)}</section><section class="ops-card company-review"><div class="ops-card-head"><div><h2>加盟商能力与服务区域审核申请</h2><p>新加盟商在创建时已自动开通；这里仅处理后续提交的能力或服务区域变更。</p></div><select class="ops-input" id="company-review-status" style="width:auto"><option value="PENDING" ${S.companyStatus==='PENDING'?'selected':''}>待审核</option><option value="APPROVED" ${S.companyStatus==='APPROVED'?'selected':''}>已通过</option><option value="REJECTED" ${S.companyStatus==='REJECTED'?'selected':''}>已驳回</option></select></div><h3>公司能力（${capabilities.total||0}）</h3>${table(['加盟商','能力','状态','审核说明','审核时间','操作'],capabilityRows)}${companyQueuePager(capabilities,'capability',S.companyCapabilityPage)}</section><section class="ops-card company-review"><h3>服务区域（${areas.total||0}）</h3>${table(['加盟商','区域','状态','审核说明','审核时间','操作'],areaRows)}${companyQueuePager(areas,'area',S.companyAreaPage)}</section>`);
  document.querySelector('#company-filter-form').onsubmit=event=>{event.preventDefault();S.companyKeyword=document.querySelector('#company-keyword').value.trim();S.companyLifecycleStatus=document.querySelector('#company-lifecycle-status').value;S.companyPage=1;companies()};
  document.querySelector('#company-filter-reset').onclick=()=>{S.companyKeyword='';S.companyLifecycleStatus='';S.companyPage=1;companies()};
  document.querySelector('#new-franchise-company').onclick=openNewFranchiseCompany;
  document.querySelector('#company-review-status').onchange=event=>{S.companyStatus=event.target.value;S.companyCapabilityPage=1;S.companyAreaPage=1;companies()};
  bindCompanyQueuePager(companyPage,'company-list','companyPage');
  bindCompanyQueuePager(capabilities,'capability','companyCapabilityPage');
  bindCompanyQueuePager(areas,'area','companyAreaPage');
  document.querySelectorAll('[data-cap-decision]').forEach(button=>button.onclick=()=>reviewCompanyCapability(button));
  document.querySelectorAll('[data-area-decision]').forEach(button=>button.onclick=()=>reviewCompanyArea(button));
  const companiesById=Object.fromEntries((companyPage.items||[]).map(company=>[company.id,company]));
  document.querySelectorAll('[data-company-edit]').forEach(button=>button.onclick=()=>editCompany(companiesById[button.dataset.companyEdit]));
  document.querySelectorAll('[data-company-accounts]').forEach(button=>button.onclick=()=>companyAccounts(button.dataset.companyAccounts,button.dataset.companyName));
}
async function openNewFranchiseCompany(){
  const cities=await platformCities();
  const provinces=[...new Map(cities.map(city=>[city.province_code,{code:city.province_code,name:city.province_name}])).values()];
  modal('新建加盟商主体',`<form class="ops-form" id="new-franchise-form"><div class="ops-notice">创建的是一间新的加盟商公司，不是给现有加盟商新增人员账号。服务范围在同一个选择框中按省、市、区县确定；区县可多选。创建完成后立即开通接单资格，并同步到加盟商 H5。</div><div class="ops-field"><label for="new-franchise-name">加盟商名称 *</label><input class="ops-input" id="new-franchise-name" maxlength="128" placeholder="例如：北京合家美宅"></div><div class="ops-field"><label for="new-franchise-owner">负责人姓名</label><input class="ops-input" id="new-franchise-owner" maxlength="64" placeholder="例如：北京负责人"></div><div class="ops-field"><label for="new-franchise-phone">联系电话</label><input class="ops-input" id="new-franchise-phone" inputmode="tel" maxlength="32"></div><div class="ops-field"><label>服务范围 *</label><div class="ops-region-picker"><button class="ops-region-summary" id="new-franchise-region-picker" type="button" aria-expanded="false">请选择省、市和区/县</button><div class="ops-region-panel" id="new-franchise-region-panel" hidden><div class="ops-row"><div class="ops-field"><label for="new-franchise-province">省份</label><select class="ops-input" id="new-franchise-province"><option value="">请选择省份</option>${provinces.map(province=>`<option value="${esc(province.code)}">${esc(province.name)}</option>`).join('')}</select></div><div class="ops-field"><label for="new-franchise-city">城市</label><select class="ops-input" id="new-franchise-city" disabled><option value="">请先选择省份</option></select></div></div><div class="ops-field"><label>区/县（可多选）</label><div class="ops-region-options" id="new-franchise-district-options"><span class="ops-muted">请先选择城市</span></div></div></div></div></div><div class="ops-field"><label for="new-franchise-notes">备注</label><textarea class="ops-textarea" id="new-franchise-notes" maxlength="500" placeholder="可记录签约或交接说明"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="new-franchise-cancel">取消</button><button class="ops-btn primary" type="submit">创建并开通</button></div></form>`,()=>{
    const form=document.querySelector('#new-franchise-form'),submit=document.querySelector('#new-franchise-form button[type="submit"]');
    document.querySelector('#new-franchise-cancel').onclick=closeModal;
    const picker=document.querySelector('#new-franchise-region-picker'),panel=document.querySelector('#new-franchise-region-panel'),provinceSelect=document.querySelector('#new-franchise-province'),citySelect=document.querySelector('#new-franchise-city'),districtOptions=document.querySelector('#new-franchise-district-options');
    const selectedDistrictCodes=()=>[...document.querySelectorAll('input[name="new-franchise-district"]:checked')].map(input=>input.value);
    const updateSummary=()=>{const province=provinces.find(item=>item.code===provinceSelect.value),city=cities.find(item=>item.code===citySelect.value),districtNames=[...document.querySelectorAll('input[name="new-franchise-district"]:checked')].map(input=>input.dataset.name);picker.textContent=province&&city&&districtNames.length?`${province.name} / ${city.name} / ${districtNames.join('、')}`:'请选择省、市和区/县'};
    picker.onclick=()=>{const opening=panel.hidden;panel.hidden=!opening;picker.setAttribute('aria-expanded',String(opening))};
    provinceSelect.onchange=()=>{const provinceCities=cities.filter(city=>city.province_code===provinceSelect.value);replacePlatformSelectOptions(citySelect,provinceCities,'','','请选择城市');citySelect.disabled=!provinceSelect.value;districtOptions.innerHTML='<span class="ops-muted">请先选择城市</span>';updateSummary()};
    citySelect.onchange=async()=>{const districts=await platformDistricts(citySelect.value);districtOptions.innerHTML=districts.length?districts.map(district=>`<label><input type="checkbox" name="new-franchise-district" value="${esc(district.code)}" data-name="${esc(district.name)}"> ${esc(district.name)}</label>`).join(''):'<span class="ops-muted">该城市暂无可选区县</span>';districtOptions.querySelectorAll('input').forEach(input=>input.onchange=updateSummary);updateSummary()};
    form.onsubmit=async event=>{event.preventDefault();const name=document.querySelector('#new-franchise-name').value.trim(),primary_city_code=citySelect.value,district_codes=selectedDistrictCodes();if(name.length<2||!provinceSelect.value||!primary_city_code||!district_codes.length){toast('请填写加盟商名称并在服务范围中选择省、市及至少一个区/县',true);return}submit.disabled=true;try{const company=await api('/companies/simple',{method:'POST',body:JSON.stringify({name,owner_name:document.querySelector('#new-franchise-owner').value.trim()||null,contact_phone:document.querySelector('#new-franchise-phone').value.trim()||null,primary_city_code,district_codes,serve_all_districts:false,notes:document.querySelector('#new-franchise-notes').value.trim()||null})});closeModal();toast(`${company.name} 已创建并开通，加盟商 H5 可立即使用`);await companies()}catch(error){submit.disabled=false;toast(error.message,true)}};
  });
}
function editCompany(company){
  if(!company)return;
  modal(`编辑${company.name}资料`,`<form class="ops-form" id="company-edit-form"><div class="ops-notice">编辑与启停会保留原公司、账号及客资历史。联系电话仅在确需变更时填写，留空不会覆盖原信息。</div><div class="ops-field"><label for="company-edit-name">公司名称 *</label><input class="ops-input" id="company-edit-name" maxlength="128" value="${esc(company.name||'')}"></div><div class="ops-field"><label for="company-edit-owner">负责人</label><input class="ops-input" id="company-edit-owner" maxlength="64" value="${esc(company.owner_name||'')}"></div><div class="ops-field"><label for="company-edit-phone">联系电话</label><input class="ops-input" id="company-edit-phone" inputmode="tel" maxlength="32" placeholder="当前：${esc(company.contact_phone_masked||'未填写')}；留空不修改"></div><div class="ops-field"><label for="company-edit-level">合作等级</label><input class="ops-input" id="company-edit-level" maxlength="32" value="${esc(company.level_code||'V1')}"></div><div class="ops-field"><label for="company-edit-status">公司状态 *</label><select class="ops-input" id="company-edit-status"><option value="ACTIVE" ${company.status==='ACTIVE'?'selected':''}>正常</option><option value="PENDING" ${company.status==='PENDING'?'selected':''}>待审核</option><option value="DISABLED" ${company.status==='DISABLED'?'selected':''}>停用</option></select></div><div class="ops-field"><label for="company-edit-notes">备注</label><textarea class="ops-textarea" id="company-edit-notes" maxlength="500">${esc(company.notes||'')}</textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="company-edit-cancel">取消</button><button class="ops-btn primary" id="company-edit-submit">保存资料</button></div></form>`,()=>{
    const form=document.querySelector('#company-edit-form'),submit=document.querySelector('#company-edit-submit');
    document.querySelector('#company-edit-cancel').onclick=closeModal;
    form.onsubmit=async event=>{event.preventDefault();const name=document.querySelector('#company-edit-name').value.trim(),phone=document.querySelector('#company-edit-phone').value.trim();if(name.length<2){toast('公司名称至少 2 个字符',true);return}submit.disabled=true;try{const body={name,owner_name:document.querySelector('#company-edit-owner').value.trim()||null,level_code:document.querySelector('#company-edit-level').value.trim()||'V1',status:document.querySelector('#company-edit-status').value,notes:document.querySelector('#company-edit-notes').value.trim()||null};if(phone)body.contact_phone=phone;await api(`/companies/${encodeURIComponent(company.id)}`,{method:'PATCH',body:JSON.stringify(body)});toast('加盟商资料已保存');closeModal();await companies()}catch(error){submit.disabled=false;toast(error.message,true)}};
  });
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
    modal(`${companyName||'加盟商'} · 账号与人员`,`${isSuperAdmin()?'<div class="ops-notice">超级管理员的开通、停用和重置操作必须填写理由，并写入审计。</div>':'<div class="ops-notice">运营可开通、停用和重置该加盟商的负责人及员工账号，所有操作均留存审计。加盟商内部客资分配不在此页面展示。</div>'}<div class="ops-actions"><button class="ops-btn primary" id="company-account-create">开通账号</button></div>${table(['姓名 / 登录账号','角色','状态','微信','操作'],rows)}`,()=>{
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
async function dispatch(){const d=await api(`/v1.2/dispatch-pool${qs({page:S.page,page_size:20})}`);const rows=(d.items||[]).map(x=>`<tr><td><b>${esc(x.customer_name)}</b><br>${esc(x.phone_masked||'--')}</td><td>${esc(x.city||'--')} ${esc(x.district||'')}</td><td>${esc(label(x.source_kind))}</td><td>${esc(x.need_summary||'--')}</td><td><button class="ops-btn primary" data-candidate="${x.id}">选择接收公司</button></td></tr>`);shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>待人工派发池</h2><p>“所在地”属于客资；加盟商的服务区域仅用于判断是否可承接。</p></div></div>${table(['客户','所在地','客资来源','客户需求','操作'],rows)}${pager(d)}</section>`);bindPager(d,dispatch);document.querySelectorAll('[data-candidate]').forEach(b=>b.onclick=()=>candidates(b.dataset.candidate));if(S.id){const id=S.id;S.id='';candidates(id)}}
async function candidates(leadId){
  modal('选择接收公司','<div class="ops-loading">正在匹配可承接的加盟商…</div>');
  let d;
  try{d=await api(`/v1.2/dispatch-pool/${encodeURIComponent(leadId)}/candidates`)}catch(error){modal('选择接收公司',`<div class="ops-error">${esc(error.message||'暂时无法获取可派发的加盟商')}</div>`);return}
  const candidates=[...(d.candidates||[])].sort((a,b)=>Number(Boolean(b.region_match))-Number(Boolean(a.region_match))||Number(Boolean(b.eligible))-Number(Boolean(a.eligible))||String(a.company_name||'').localeCompare(String(b.company_name||''),'zh-CN'));
  const rowsFor=keyword=>candidates.filter(item=>String(item.company_name||'').toLowerCase().includes(keyword.toLowerCase())).map(x=>{const returnedReceiver=(x.exclusion_reasons||[]).includes('RETURNED_RECEIVER_EXCLUDED');const onlyReturnedReceiver=returnedReceiver&&(x.exclusion_reasons||[]).length===1;const action=x.eligible?`<button class="ops-btn primary" data-dispatch="${esc(x.company_id)}">派发</button>`:onlyReturnedReceiver?`<button class="ops-btn" data-dispatch-override="${esc(x.company_id)}">例外派发</button>`:'--';return `<tr><td><b>${esc(x.company_name)}</b><br><small>${x.region_match?'与所在地匹配':'其他服务区域'}</small></td><td>${x.eligible?badge('APPROVED'):badge('REJECTED')}</td><td>${x.points_price}</td><td>${x.points_available??'按权限隐藏'}</td><td>${esc(candidateReasons(x.exclusion_reasons))}</td><td>${action}</td></tr>`});
  const draw=keyword=>table(['接收公司','是否可派','所需积分','可用积分','判断说明','操作'],rowsFor(keyword));
  modal('选择接收公司',`<div class="ops-notice">按所在地优先展示可承接的加盟商；也可以搜索其他加盟商。曾领取后退回的原公司默认不可再次派发，确需例外派发时必须填写运营判断原因并保留审计。</div><div class="ops-filter"><input class="ops-input" id="candidate-search" placeholder="搜索其他加盟商" autocomplete="off"></div><div id="candidate-results">${draw('')}</div>`,()=>{
    const result=document.querySelector('#candidate-results');
    const bindActions=()=>{document.querySelectorAll('[data-dispatch]').forEach(b=>b.onclick=()=>dispatchOne(leadId,b.dataset.dispatch));document.querySelectorAll('[data-dispatch-override]').forEach(b=>b.onclick=()=>dispatchOne(leadId,b.dataset.dispatchOverride,true))};
    document.querySelector('#candidate-search').oninput=event=>{zsSetSafeHtml(result,draw(event.target.value.trim()));bindActions()};
    bindActions();
  });
}
function dispatchOne(leadId,companyId,returnReceiverOverride=false){actionForm({title:returnReceiverOverride?'确认例外派发':'确认人工派发',message:returnReceiverOverride?'该公司曾领取后退回本条客资。请写明运营复核后仍允许再次派发的例外原因。':'请再次核对接收公司。提交后会生成派发单并记录审计。',labelText:returnReceiverOverride?'例外派发原因':'派发备注',required:returnReceiverOverride,minLength:returnReceiverOverride?2:undefined,submitLabel:returnReceiverOverride?'确认例外派发':'确认派发'},async note=>{await api(`/v1.2/dispatch-pool/${encodeURIComponent(leadId)}/dispatch`,{method:'POST',body:JSON.stringify({company_id:companyId,idempotency_key:`dispatch-${crypto.randomUUID()}`,note:returnReceiverOverride?null:note||null,return_receiver_override:returnReceiverOverride,return_receiver_override_reason:returnReceiverOverride?note:null})});toast('客资已派发');await dispatch()})}
async function returns(){const [d,t]=await Promise.all([api(`/v1.2/returns${qs({status:S.status,page:S.page,page_size:20})}`),can('verification.read')?api('/v1.2/return-verifications/tasks?page=1&page_size=100'):Promise.resolve({items:[]})]);if(can('verification.read'))await loadTelesalesUsers();const rows=(d.items||[]).map(x=>`<tr><td>${esc(recordCode(x.id,'TH'))}<br><small>派发编号 ${esc(recordCode(x.assignment_id,'PF'))}</small></td><td>${esc(label(x.reason_code))}</td><td>${badge(x.status)}</td><td>${fmt(x.submitted_at||x.created_at)}</td><td><button class="ops-btn" data-return="${x.id}">查看与审核</button></td></tr>`);const tasks=(t.items||[]).map(x=>{const r=x.return_request||{},lead=x.lead||{},nextStep=x.is_overdue?'已超时，需运营改派':'电销完成退回事实核验';return `<tr><td><b>${esc(lead.customer_name||'待核验客户')}</b><br><small>${esc(lead.phone_masked||'--')}</small></td><td>${verificationTaskBadge(x)}</td><td>${esc(telesalesName(x.assignee_user_id))}</td><td>${esc(label(r.reason_code))}</td><td>${esc(nextStep)}</td><td>${fmt(x.due_at)}</td><td><button class="ops-btn" data-task="${x.id}">查看</button> <button class="ops-btn" data-assign="${x.id}">${x.assignee_user_id?'重新分配':'分配人员'}</button></td></tr>`});const filterNotice=S.status?`<div class="ops-notice">当前筛选：${esc(label(S.status))} <button class="ops-btn" id="returns-clear">查看全部</button></div>`:'';shell(`${filterNotice}<section class="ops-card"><h2>退回申诉</h2>${table(['退回编号','退回原因','处理状态','申诉时间','操作'],rows)}${pager(d)}</section>${can('verification.read')?`<section class="ops-card"><h2>电话核验任务</h2><p>仅在加盟商发起退回申诉后进行电话核验。</p>${table(['客户','状态','核验人员','退回原因','下一步','核验截止','操作'],tasks)}</section>`:''}`);bindPager(d,returns);document.querySelector('#returns-clear')?.addEventListener('click',()=>go('returns'));document.querySelectorAll('[data-return]').forEach(b=>b.onclick=()=>returnDetail(b.dataset.return));document.querySelectorAll('[data-task]').forEach(b=>b.onclick=()=>taskDetail(b.dataset.task));document.querySelectorAll('[data-assign]').forEach(b=>b.onclick=()=>assignTask(b.dataset.assign));if(S.id){const id=S.id;S.id='';returnDetail(id)}}
async function returnDetail(id){const x=await api(`/v1.2/returns/${encodeURIComponent(id)}`);if(can('verification.read'))await loadTelesalesUsers();const verification=x.verification||{},reward=x.reward||{};const canFinalReview=can('return.review')&&x.status==='REVIEWING'&&verification.conclusion;const fundImpact=x.status==='APPROVED'?`已返还 ${Number(x.refund_points||0)} 积分`:'终审通过后按原领取流水返还积分';modal('退回申诉详情',`<div class="ops-detail-grid">${[['退回编号',recordCode(x.id,'TH')],['派发编号',recordCode(x.assignment_id,'PF')],['处理状态',label(x.status)],['退回原因',label(x.reason_code)],['核验人员',telesalesName(verification.assignee_user_id)],['核验状态',label(verification.status)],['联系结果',label(verification.contact_result)],['核验结论',label(verification.conclusion)],['申诉截止',fmt(x.appeal_deadline_at)],['资金影响',fundImpact],['供资奖励',reward.status?label(reward.status):'无关联奖励'],['终审说明',x.final_decision_reason]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>申诉说明</h3><p>${esc(x.description||'暂无说明')}</p></section><section class="ops-card"><h3>申诉证据</h3><div class="ops-detail-grid">${evidenceList(x.evidences)}</div></section>${canFinalReview?'<div class="ops-actions"><button class="ops-btn primary" data-final="APPROVE">通过退回</button><button class="ops-btn danger" data-final="REJECT">驳回申诉</button><button class="ops-btn" data-final="NEED_MORE">要求补充证据</button></div>':x.status==='REVIEWING'?'<div class="ops-notice">等待电销提交事实核验结论后，才能进行运营终审。</div>':''}`,()=>document.querySelectorAll('[data-final]').forEach(b=>b.onclick=()=>finalReview(id,b.dataset.final)))}
function finalReview(id,decision){const actionLabel={APPROVE:'通过退回',REJECT:'驳回申诉',NEED_MORE:'要求补充证据'}[decision]||'提交终审';actionForm({title:actionLabel,message:'终审会影响积分返还与申诉状态，请写明判断依据。',labelText:'终审说明',required:true,minLength:2,submitLabel:`确认${actionLabel}`,danger:decision==='REJECT'},async note=>{await api(`/v1.2/returns/${encodeURIComponent(id)}/final-review`,{method:'POST',body:JSON.stringify({decision,note})});toast('终审完成');await returns()})}
async function taskDetail(id){const x=await api(`/v1.2/return-verifications/tasks/${encodeURIComponent(id)}`);await loadTelesalesUsers();const r=x.return_request||{},lead=x.lead||{},evidenceTotal=Object.values(r.evidence_summary||{}).reduce((sum,count)=>sum+Number(count||0),0);modal('电话核验详情',`<div class="ops-detail-grid">${[['客户',lead.customer_name],['联系电话',lead.phone||lead.phone_masked],['所在地',`${lead.city||''} ${lead.district||''}`],['任务状态',verificationTaskLabel(x)],['核验人员',telesalesName(x.assignee_user_id)],['退回原因',label(r.reason_code)],['证据数量',`${evidenceTotal} 份`],['核验截止',fmt(x.due_at)],['申诉截止',fmt(r.appeal_deadline_at)],['联系结果',label(x.contact_result)],['核验结论',label(x.conclusion)]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>申诉说明</h3><p>${esc(r.description||'暂无说明')}</p></section>`)}
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
  const [companyPage,activePackages,allPackages,priceRules,ledgerPage,rewardPage,frozenRewardPage,currentRewardRule,cities]=await Promise.all([
    api(`/companies${qs({keyword:S.financeCompanyKeyword,status:S.financeCompanyStatus,page:S.financeCompanyPage,page_size:20})}`),
    api('/points/packages?active_only=true'),
    api('/points/packages?active_only=false'),
    api('/points/price-rules'),
    api(`/points/ledgers${qs({company_id:S.financeCompanyId||undefined,ledger_type:S.financeLedgerType||undefined,page:S.page,page_size:20})}`),
    api(`/v1.2/supplier-rewards${qs({supplier_company_id:S.financeCompanyId||undefined,page:S.financeRewardPage,page_size:20})}`),
    api('/v1.2/supplier-rewards?status=FROZEN&page=1&page_size=1'),
    api('/v1.2/admin/supplier-reward-rules/current'),
    platformCities(),
  ]);
  const companies=companyPage.items||[];
  const companyNames=new Map(companies.map(company=>[company.id,company.name]));
  const cityNames=new Map((cities||[]).map(city=>[city.code,city.name]));
  const frozenRewards=Number(frozenRewardPage.total||0);
  const selectedCompany=companies.find(company=>company.id===S.financeCompanyId);
  const selectedCompanyLabel=selectedCompany?.name||'所选加盟商';
  const financeCompanyPages=Math.max(1,Math.ceil((companyPage.total||0)/(companyPage.page_size||20)));
  const companyRows=companies.map(company=>`<tr><td><b>${esc(company.name)}</b><br><small>${esc(company.code)}</small></td><td>${badge(company.status)}</td><td>${esc(company.points_balance??0)}</td><td>${company.id===S.financeCompanyId?'<span class="ops-status ok">正在查看</span>':'<button class="ops-btn" data-finance-company="'+esc(company.id)+'">查看账户</button>'} <button class="ops-btn" data-reconcile-company="${esc(company.id)}">核对账目</button> <button class="ops-btn" data-adjust-company="${esc(company.id)}">人工调账</button> <button class="ops-btn primary" data-recharge-company="${esc(company.id)}">线下充值</button></td></tr>`);
  const packageRows=(allPackages||[]).map(item=>`<tr><td>${esc(item.name)}<br><small>${esc(item.code)} · V${esc(item.version)}</small></td><td>${Number(item.cash_amount_cents||0)/100} 元</td><td>${esc(item.base_points)}</td><td>${esc(item.bonus_points)}</td><td>${esc(item.total_points)}</td><td>${badge(item.status)}</td></tr>`);
  const priceRows=(priceRules||[]).map(item=>`<tr><td>${esc(item.region_code?cityNames.get(item.region_code)||item.region_code:'全部地区')}</td><td>${esc(item.category_code||'全部类目')}</td><td>${esc(item.brand_code||'全部品牌')}</td><td>${esc(item.level_code||'全部等级')}</td><td>${esc(item.points_cost)}</td><td>${badge(item.status)}</td></tr>`);
  const ledgerRows=(ledgerPage.items||[]).map(ledger=>{const ledgerType=ledger.ledger_type||ledger.type;const reversible=['RECHARGE','ADJUST'].includes(ledgerType);return `<tr><td>${fmt(ledger.created_at)}</td><td>${esc(companyNames.get(ledger.company_id)||recordCode(ledger.company_id,'加盟商'))}</td><td>${esc(label(ledgerType))}</td><td>${esc(ledger.delta>0?`+${ledger.delta}`:ledger.delta)}</td><td>${esc(ledger.balance_after)}</td><td>${esc(ledger.external_reference||'--')}</td><td>${reversible?`<button class="ops-btn danger" data-ledger-reverse="${esc(ledger.id)}">冲正</button>`:'业务流程处理'}</td></tr>`});
  shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>资金治理</h2><p>仅超级管理员可写入资金。充值、调账、冲正不要求第二位超级管理员复核，但必须保留关联公司、金额或积分、凭证说明和审计记录。</p></div></div><div class="ops-detail-grid"><div class="ops-detail"><small>加盟商账户</small><b>${companyPage.total||0} 家</b></div><div class="ops-detail"><small>冻结供客奖励</small><b>${frozenRewards} 笔</b></div><div class="ops-detail"><small>当前查看</small><b>${esc(S.financeCompanyId?selectedCompanyLabel:'全部加盟商')}</b></div></div></section><section class="ops-card"><div class="ops-card-head"><div><h2>加盟商积分账户</h2><p>通过公司名称、编号或状态快速定位。先核对账目，再进行充值或调账；不允许编辑历史流水。</p></div></div><form class="ops-filter" id="finance-company-filter"><input class="ops-input" id="finance-company-keyword" value="${esc(S.financeCompanyKeyword)}" placeholder="搜索公司名称或编号"><select class="ops-input" id="finance-company-status"><option value="" ${S.financeCompanyStatus===''?'selected':''}>全部状态</option><option value="ACTIVE" ${S.financeCompanyStatus==='ACTIVE'?'selected':''}>正常</option><option value="PENDING" ${S.financeCompanyStatus==='PENDING'?'selected':''}>待审核</option><option value="DISABLED" ${S.financeCompanyStatus==='DISABLED'?'selected':''}>已停用</option></select><button class="ops-btn primary" type="submit">查询</button><button class="ops-btn" type="button" id="finance-company-reset">重置</button>${S.financeCompanyId?'<button class="ops-btn" type="button" id="finance-company-clear">查看全部账户</button>':''}</form>${table(['加盟商','状态','当前积分','操作'],companyRows)}<div class="ops-pager"><button class="ops-btn" id="finance-company-prev" ${S.financeCompanyPage<=1?'disabled':''}>上一页</button><span>${S.financeCompanyPage}/${financeCompanyPages}，共 ${companyPage.total||0} 家</span><button class="ops-btn" id="finance-company-next" ${S.financeCompanyPage>=financeCompanyPages?'disabled':''}>下一页</button></div></section><section class="ops-card"><div class="ops-card-head"><h2>充值档位</h2><button class="ops-btn primary" id="new-package">新增充值档位</button></div>${table(['档位','线下实收','基础积分','赠送积分','到账积分','状态'],packageRows)}</section><section class="ops-card"><div class="ops-card-head"><h2>客资积分价格</h2><button class="ops-btn primary" id="new-price-rule">新增价格规则</button></div>${table(['适用地区','业务类目','品牌','加盟商等级','领取积分','状态'],priceRows)}</section><section class="ops-card"><div class="ops-card-head"><div><h2>积分流水</h2><p>只允许冲正人工充值和人工调账；领取、退回与奖励须经相应业务流程处理。</p></div><select class="ops-input" id="finance-ledger-type" style="width:auto"><option value="" ${S.financeLedgerType===''?'selected':''}>全部类型</option><option value="RECHARGE" ${S.financeLedgerType==='RECHARGE'?'selected':''}>充值</option><option value="ADJUST" ${S.financeLedgerType==='ADJUST'?'selected':''}>人工调整</option><option value="REVERSE" ${S.financeLedgerType==='REVERSE'?'selected':''}>冲正</option></select></div>${table(['时间','加盟商','类型','变化','余额','外部凭据','操作'],ledgerRows)}${pager(ledgerPage)}</section>${rewardSection(rewardPage,currentRewardRule)}`);
  bindPager(ledgerPage,finance);
  document.querySelector('#finance-company-filter').onsubmit=event=>{event.preventDefault();S.financeCompanyKeyword=document.querySelector('#finance-company-keyword').value.trim();S.financeCompanyStatus=document.querySelector('#finance-company-status').value;S.financeCompanyPage=1;finance()};
  document.querySelector('#finance-company-reset').onclick=()=>{S.financeCompanyKeyword='';S.financeCompanyStatus='';S.financeCompanyPage=1;finance()};
  document.querySelector('#finance-company-clear')?.addEventListener('click',()=>{S.financeCompanyId='';S.financeRewardPage=1;S.page=1;finance()});
  document.querySelector('#finance-company-prev').onclick=()=>{S.financeCompanyPage=Math.max(1,S.financeCompanyPage-1);finance()};
  document.querySelector('#finance-company-next').onclick=()=>{S.financeCompanyPage=Math.min(financeCompanyPages,S.financeCompanyPage+1);finance()};
  document.querySelector('#finance-ledger-type').onchange=event=>{S.financeLedgerType=event.target.value;S.page=1;finance()};
  document.querySelectorAll('[data-finance-company]').forEach(button=>button.onclick=()=>{S.financeCompanyId=button.dataset.financeCompany;S.financeRewardPage=1;S.page=1;finance()});
  document.querySelectorAll('[data-reconcile-company]').forEach(button=>button.onclick=()=>reconcileCompanyPoints(button.dataset.reconcileCompany,companies));
  document.querySelectorAll('[data-adjust-company]').forEach(button=>button.onclick=()=>adjustCompanyPoints(button.dataset.adjustCompany,companies));
  document.querySelectorAll('[data-recharge-company]').forEach(button=>button.onclick=()=>rechargeCompanyPoints(button.dataset.rechargeCompany,companies,activePackages));
  document.querySelectorAll('[data-ledger-reverse]').forEach(button=>button.onclick=()=>reverseLedger(button.dataset.ledgerReverse));
  document.querySelector('#new-package').onclick=newPointsPackage;
  document.querySelector('#new-price-rule').onclick=newPriceRule;
  bindRewardActions(currentRewardRule);
}
function rechargeCompanyPoints(companyId,companies,packages){
  const company=companies.find(item=>item.id===companyId);
  const options=packages.map(item=>`<option value="${esc(item.id)}" data-cash="${Number(item.cash_amount_cents)}">${esc(item.name)} · ${Number(item.total_points)} 积分</option>`).join('');
  if(!options){toast('当前没有可用的积分充值档位，请先配置档位',true);return}
  modal(`为${company?.name||'加盟商'}充值积分`,`<form class="ops-form" id="recharge-form"><div class="ops-notice">请先完成线下收款核实。本操作无需第二位超级管理员复核，但会记录操作人、充值档位、外部凭据与审计。</div><div class="ops-field"><label for="recharge-package">充值档位 *</label><select class="ops-input" id="recharge-package">${options}</select></div><div class="ops-field"><label for="recharge-reference">外部收款凭据号 *</label><input class="ops-input" id="recharge-reference" minlength="3" maxlength="128" placeholder="例如：银行流水号或收款单号"></div><div class="ops-field"><label for="recharge-note">收款核验与凭证说明 *</label><textarea class="ops-textarea" id="recharge-note" minlength="3" maxlength="500" placeholder="填写核验人、凭证位置及到账确认结果"></textarea></div><label class="ops-check"><input type="checkbox" id="recharge-confirmed"> 我已核实本笔线下款项</label><div class="ops-actions"><button class="ops-btn" type="button" id="recharge-cancel">取消</button><button class="ops-btn primary" id="recharge-submit">确认充值</button></div></form>`,()=>{
    const form=document.querySelector('#recharge-form');
    document.querySelector('#recharge-cancel').onclick=closeModal;
    form.onsubmit=async event=>{
      event.preventDefault();
      const packageSelect=document.querySelector('#recharge-package');
      const external_reference=document.querySelector('#recharge-reference').value.trim();
      const note=document.querySelector('#recharge-note').value.trim();
      const confirmed=document.querySelector('#recharge-confirmed').checked;
      const submit=document.querySelector('#recharge-submit');
      if(external_reference.length<3){toast('请填写至少 3 个字符的外部收款凭据号',true);return}
      if(note.length<3){toast('请填写至少 3 个字符的收款核验与凭证说明',true);return}
      if(!confirmed){toast('请确认已核实线下款项',true);return}
      submit.disabled=true;
      try{
        await api('/points/recharge',{method:'POST',body:JSON.stringify({company_id:companyId,package_id:packageSelect.value,cash_amount_cents:Number(packageSelect.selectedOptions[0].dataset.cash),external_reference,note,idempotency_key:`recharge-${crypto.randomUUID()}`,confirmed:true})});
        toast('积分充值已入账');
        closeModal();
        await finance();
      }catch(error){submit.disabled=false;toast(error.message,true)}
    };
  });
}
function reconcileCompanyPoints(companyId,companies){
  const company=companies.find(item=>item.id===companyId);
  api(`/points/reconciliation/${encodeURIComponent(companyId)}`).then(result=>{
    const status=result.balanced?'账目一致':'发现对账差异';
    modal(`${company?.name||'加盟商'} · ${status}`,`<div class="ops-detail-grid">${[['流水期末余额',result.expected_closing_balance],['账户快照余额',result.snapshot_balance],['余额差异',result.difference],['流水顺序异常',result.sequence_error_count]].map(([name,value])=>`<div class="ops-detail"><small>${name}</small><b>${esc(value)}</b></div>`).join('')}</div><div class="ops-notice">${result.balanced?'余额、流水与顺序均已核对一致。':'发现差异，请停止人工资金写入，并依据审计记录和不可变流水排查。'}</div>`);
    toast(result.balanced?'积分对账一致':'发现对账异常，请处理',!result.balanced);
  }).catch(error=>toast(error.message,true));
}
function adjustCompanyPoints(companyId,companies){
  const company=companies.find(item=>item.id===companyId);
  modal(`为${company?.name||'加盟商'}人工调账`,`<form class="ops-form" id="adjust-form"><div class="ops-notice">调整会生成不可变流水。请填写关联公司、正负积分值和可复核的原因或凭证说明。</div><div class="ops-field"><label for="adjust-delta">调整积分 *</label><input class="ops-input" id="adjust-delta" type="number" inputmode="numeric" placeholder="正数增加，负数扣减"></div><div class="ops-field"><label for="adjust-reason">调账原因及凭证说明 *</label><textarea class="ops-textarea" id="adjust-reason" minlength="3" maxlength="500"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="adjust-cancel">取消</button><button class="ops-btn primary" id="adjust-submit">确认调账</button></div></form>`,()=>{
    const form=document.querySelector('#adjust-form');
    document.querySelector('#adjust-cancel').onclick=closeModal;
    form.onsubmit=async event=>{event.preventDefault();const delta=Number(document.querySelector('#adjust-delta').value),reason=document.querySelector('#adjust-reason').value.trim(),submit=document.querySelector('#adjust-submit');if(!Number.isInteger(delta)||delta===0){toast('请输入非零整数积分',true);return}if(reason.length<3){toast('请填写至少 3 个字符的调账原因及凭证说明',true);return}submit.disabled=true;try{await api('/points/adjust',{method:'POST',body:JSON.stringify({company_id:companyId,delta,reason,idempotency_key:`adjust-${crypto.randomUUID()}`})});toast('人工调账已入账');closeModal();await finance()}catch(error){submit.disabled=false;toast(error.message,true)}};
  });
}
function reverseLedger(ledgerId){
  actionForm({title:'确认冲正人工流水',message:'冲正会生成反向流水，不会编辑或删除历史记录。仅人工充值和人工调账可从此处冲正。',labelText:'冲正原因及凭证说明',required:true,minLength:3,submitLabel:'确认冲正',danger:true},async reason=>{await api(`/points/ledgers/${encodeURIComponent(ledgerId)}/reverse`,{method:'POST',body:JSON.stringify({reason,idempotency_key:`reverse-${crypto.randomUUID()}`})});toast('积分流水已冲正');await finance()});
}
function newPointsPackage(){
  modal('新增充值档位',`<form class="ops-form" id="package-form"><div class="ops-field"><label for="package-code">档位代码 *</label><input class="ops-input" id="package-code" maxlength="64" placeholder="例如：V2-50000"></div><div class="ops-field"><label for="package-name">档位名称 *</label><input class="ops-input" id="package-name" maxlength="128" placeholder="例如：5 万积分标准档"></div><div class="ops-field"><label for="package-cash">线下实收金额（元） *</label><input class="ops-input" id="package-cash" type="number" min="0" step="0.01"></div><div class="ops-field"><label for="package-base">基础积分 *</label><input class="ops-input" id="package-base" type="number" min="1" step="1"></div><div class="ops-field"><label for="package-bonus">赠送积分</label><input class="ops-input" id="package-bonus" type="number" min="0" step="1" value="0"></div><div class="ops-field"><label for="package-level">适用等级</label><input class="ops-input" id="package-level" maxlength="32" value="V1"></div><div class="ops-field"><label for="package-entitlement">权益说明</label><textarea class="ops-textarea" id="package-entitlement" maxlength="500"></textarea></div><div class="ops-actions"><button class="ops-btn" type="button" id="package-cancel">取消</button><button class="ops-btn primary" id="package-submit">保存并发布</button></div></form>`,()=>{
    const form=document.querySelector('#package-form');document.querySelector('#package-cancel').onclick=closeModal;
    form.onsubmit=async event=>{event.preventDefault();const code=document.querySelector('#package-code').value.trim(),name=document.querySelector('#package-name').value.trim(),cash=Math.round(Number(document.querySelector('#package-cash').value)*100),base=Number(document.querySelector('#package-base').value),bonus=Number(document.querySelector('#package-bonus').value||0),level=document.querySelector('#package-level').value.trim()||'V1',benefit=document.querySelector('#package-entitlement').value.trim(),submit=document.querySelector('#package-submit');if(code.length<2||name.length<2||!Number.isInteger(cash)||cash<0||!Number.isInteger(base)||base<=0||!Number.isInteger(bonus)||bonus<0){toast('请完整填写充值档位信息',true);return}submit.disabled=true;try{await api('/points/packages',{method:'POST',body:JSON.stringify({code,name,cash_amount_cents:cash,base_points:base,bonus_points:bonus,level_code:level,entitlements:benefit?{benefit_summary:benefit}:{},publish:true})});toast('充值档位已发布');closeModal();await finance()}catch(error){submit.disabled=false;toast(error.message,true)}};
  });
}
function priceRulePriority(values){return 1000-(values.region_code?300:0)-(values.category_code?200:0)-(values.brand_code?100:0)-(values.level_code?50:0)}
async function newPriceRule(){
  const [cities,categories,brands]=await Promise.all([
    platformCities(),
    api('/master-data/dictionaries/lead_category'),
    api('/master-data/dictionaries/brand'),
  ]);
  const cityOptions=`<option value="">全部地区</option>${cities.map(city=>`<option value="${esc(city.code)}">${esc(city.name)}</option>`).join('')}`;
  const dictionaryOptions=(items,label)=>`<option value="">${label}</option>${items.map(item=>`<option value="${esc(item.code)}">${esc(item.label)}</option>`).join('')}`;
  modal('新增客资积分价格规则',`<form class="ops-form" id="price-rule-form"><div class="ops-notice">字段留空表示“全部”，系统会优先匹配地区、类目、品牌和等级更具体的已发布规则。</div><div class="ops-field"><label for="rule-region">适用地区</label><select class="ops-input" id="rule-region">${cityOptions}</select></div><div class="ops-field"><label for="rule-category">业务类目</label><select class="ops-input" id="rule-category">${dictionaryOptions(categories,'全部类目')}</select></div><div class="ops-field"><label for="rule-brand">品牌</label><select class="ops-input" id="rule-brand">${dictionaryOptions(brands,'全部品牌')}</select></div><div class="ops-field"><label for="rule-level">加盟商等级</label><select class="ops-input" id="rule-level"><option value="">全部等级</option><option value="V1">V1</option><option value="V2">V2</option><option value="V3">V3</option></select></div><div class="ops-field"><label for="rule-cost">领取所需积分 *</label><input class="ops-input" id="rule-cost" type="number" min="1" step="1"></div><div class="ops-actions"><button class="ops-btn" type="button" id="price-rule-cancel">取消</button><button class="ops-btn primary" id="price-rule-submit">保存并发布</button></div></form>`,()=>{
    const form=document.querySelector('#price-rule-form');document.querySelector('#price-rule-cancel').onclick=closeModal;
    form.onsubmit=async event=>{event.preventDefault();const values={region_code:document.querySelector('#rule-region').value||null,category_code:document.querySelector('#rule-category').value||null,brand_code:document.querySelector('#rule-brand').value||null,level_code:document.querySelector('#rule-level').value||null},points_cost=Number(document.querySelector('#rule-cost').value),submit=document.querySelector('#price-rule-submit');if(!Number.isInteger(points_cost)||points_cost<=0){toast('请输入正整数领取积分',true);return}submit.disabled=true;try{await api('/points/price-rules',{method:'POST',body:JSON.stringify({...values,points_cost,priority:priceRulePriority(values),publish:true})});toast('积分价格规则已发布');closeModal();await finance()}catch(error){submit.disabled=false;toast(error.message,true)}};
  });
}
function ruleSummary(rule){const ratio=(Number(rule?.ratio_bps||0)/100).toFixed(2).replace(/\.00$/,'');const max=rule?.max_points==null?'不设上限':`${rule.max_points} 积分`;return `<div class="ops-detail-grid">${[['奖励比例',`${ratio}%`],['最低奖励',`${rule?.min_points||0} 积分`],['最高奖励',max],['同一客户短期重复',`${rule?.hard_duplicate_days||0} 天内不计奖励`],['再次获得奖励',`${rule?.reward_duplicate_days||0} 天后`],['历史记录提醒',`查看 ${rule?.historical_suspect_days||0} 天内记录`]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b)}</b></div>`).join('')}</div>`}
function rewardSection(pageData,currentRule){const rows=(pageData.items||[]).map(item=>`<tr><td>${esc(recordCode(item.id,'JL'))}<br><small>派发编号 ${esc(recordCode(item.assignment_id,'PF'))}</small></td><td>${esc(recordCode(item.supplier_company_id,'加盟商'))}</td><td>${item.claim_points}</td><td>${item.reward_points}</td><td>${badge(item.status)}</td><td>${fmt(item.reward_due_at)}</td><td><button class="ops-btn" data-reward="${item.id}">查看</button>${item.status==='OBSERVING'?` <button class="ops-btn primary" data-settle="${item.id}">结算</button>`:''}${item.status==='SETTLED'?` <button class="ops-btn danger" data-reverse="${item.id}">撤销奖励</button>`:''}</td></tr>`);const pages=Math.max(1,Math.ceil((pageData.total||0)/(pageData.page_size||20)));const pager=`<div class="ops-pager"><button class="ops-btn" id="finance-reward-prev" ${S.financeRewardPage<=1?'disabled':''}>上一页</button><span>${S.financeRewardPage}/${pages}，共 ${pageData.total||0} 条</span><button class="ops-btn" id="finance-reward-next" ${S.financeRewardPage>=pages?'disabled':''}>下一页</button></div>`;return `${currentRule?`<section class="ops-card"><div class="ops-card-head"><div><h2>供客奖励规则</h2><p>奖励只结算给提交客资的加盟商；领取客资的加盟商不获得供客奖励。</p></div></div>${ruleSummary(currentRule)}<div class="ops-actions"><button class="ops-btn" id="new-rule">调整奖励比例</button><button class="ops-btn gold" id="settle-due">结算已到期奖励</button></div></section>`:''}<section class="ops-card"><div class="ops-card-head"><div><h2>供客奖励明细</h2><p>按客资提供方查看奖励；退回申诉成立时奖励冻结或取消。</p></div></div>${table(['奖励编号','客资提供方','领取积分','奖励积分','状态','预计结算','操作'],rows)}${pager}</section>`}
function bindRewardActions(currentRule){document.querySelectorAll('[data-reward]').forEach(button=>button.onclick=()=>rewardDetail(button.dataset.reward));document.querySelectorAll('[data-settle]').forEach(button=>button.onclick=()=>settle(button.dataset.settle));document.querySelectorAll('[data-reverse]').forEach(button=>button.onclick=()=>reverse(button.dataset.reverse));document.querySelector('#settle-due')?.addEventListener('click',settleDue);document.querySelector('#new-rule')?.addEventListener('click',()=>newRule(currentRule));document.querySelector('#finance-reward-prev')?.addEventListener('click',()=>{if(S.financeRewardPage>1){S.financeRewardPage--;finance()}});document.querySelector('#finance-reward-next')?.addEventListener('click',()=>{S.financeRewardPage++;finance()});if(S.id){const id=S.id;S.id='';rewardDetail(id)}}
async function rewardDetail(id){const x=await api(`/v1.2/supplier-rewards/${encodeURIComponent(id)}`);modal('奖励详情',`<div class="ops-detail-grid">${[['奖励编号',recordCode(x.id,'JL')],['派发编号',recordCode(x.assignment_id,'PF')],['加盟商',recordCode(x.supplier_company_id,'加盟商')],['接收公司',recordCode(x.receiver_company_id,'加盟商')],['状态',label(x.status)],['领取积分',x.claim_points],['奖励积分',x.reward_points],['预计结算',fmt(x.reward_due_at)],['实际到账',fmt(x.settled_at)]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>本笔奖励适用规则</h3>${ruleSummary(x.rule_snapshot||{})}</section><button class="ops-btn" id="trace">查看客资详情</button>`,()=>document.querySelector('#trace').onclick=()=>{closeModal();go('trace',id)})}
function settle(id){actionForm({title:'确认奖励结算',message:'请核对奖励状态、关联加盟商和积分金额。结算会写入不可变流水与审计。',labelText:'结算说明',required:true,minLength:3,submitLabel:'确认结算'},async note=>{await api(`/v1.2/admin/supplier-rewards/${encodeURIComponent(id)}/settle`,{method:'POST',body:JSON.stringify({note})});toast('结算指令已执行');await finance()})}
function settleDue(){actionForm({title:'结算已到期奖励',message:'仅结算符合到期条件的奖励；冻结奖励不会入账。请填写本批处理的核验说明。',labelText:'批量结算说明',required:true,minLength:3,submitLabel:'确认批量结算'},async note=>{await api('/v1.2/admin/supplier-rewards/settle-due',{method:'POST',body:JSON.stringify({limit:500,note})});toast('到期奖励结算已执行');await finance()})}
function reverse(id){actionForm({title:'确认奖励冲正',message:'冲正会生成反向流水，不会修改或删除历史记录。',labelText:'冲正原因及凭证说明',required:true,minLength:5,submitLabel:'确认冲正',danger:true},async note=>{await api(`/v1.2/admin/supplier-rewards/${encodeURIComponent(id)}/reverse`,{method:'POST',body:JSON.stringify({reason_code:'ADMIN_ERROR',note})});toast('奖励已冲正');await finance()})}
function newRule(currentRule){const currentRatio=Number(currentRule?.ratio_bps||0)/100;actionForm({title:'调整奖励比例',message:'新比例只影响规则发布后产生的奖励，历史奖励继续使用原规则。',labelText:'奖励比例（%）',value:String(currentRatio),inputType:'number',submitLabel:'发布新比例',validate:raw=>{const ratio=Number(raw);return Number.isFinite(ratio)&&ratio>0&&ratio<=100?'':'请输入 0 到 100 之间的奖励比例'}},async input=>{const ratio=Number(input);await api('/v1.2/admin/supplier-reward-rules',{method:'POST',body:JSON.stringify({ratio_bps:Math.round(ratio*100),min_points:currentRule.min_points,max_points:currentRule.max_points,hard_duplicate_days:currentRule.hard_duplicate_days,reward_duplicate_days:currentRule.reward_duplicate_days,historical_suspect_days:currentRule.historical_suspect_days,publish_immediately:true})});toast('奖励比例已更新');await finance()})}
function notificationFailureAdvice(item){if(item.status==='MANUAL_ACTION_REQUIRED')return '请检查接收人是否已绑定微信，以及对应消息模板是否已启用。';if(item.status==='DEAD')return '系统多次发送未成功，请检查消息配置后重新发送。';return '系统发送未成功，可确认配置后重新发送。'}
function notificationFailureDetail(item){
  modal('通知异常详情',`<div class="ops-detail-grid">${[['通知事项',notificationEventLabel(item.event_type)],['当前状态',notificationStatusLabel(item.status)],['已尝试',`${item.attempts||0} 次`],['创建时间',fmt(item.created_at)],['处理建议',notificationFailureAdvice(item)],['通知编号',recordCode(item.id,'TZ')]].map(([name,value])=>`<div class="ops-detail"><small>${esc(name)}</small><b>${esc(value)}</b></div>`).join('')}</div><div class="ops-notice">请先确认接收人绑定与模板配置，再重新发送。系统底层报错不会作为业务说明直接展示。</div><div class="ops-actions"><button class="ops-btn primary" id="retry-notification">重新发送</button></div>`,()=>document.querySelector('#retry-notification').onclick=async()=>{try{await retryOutbox(item.id);closeModal()}catch(error){toast(error.message,true)}});
}
async function retryOutbox(outboxId){await api(`/notifications/outbox/${encodeURIComponent(outboxId)}/retry`,{method:'POST'});toast('已加入重新发送队列');await audit()}
const AUDIT_FIELD_LABEL={name:'名称',status:'状态',reason:'处理说明',note:'处理说明',username:'登录账号',display_name:'姓名',role_code:'角色',company_id:'加盟商',lead_id:'客资',assignment_id:'派发单',return_id:'退回申诉',points:'积分',points_cost:'所需积分',source_kind:'客资来源',review_status:'审核结果',region_code:'所在地',contact_result:'联系结果',conclusion:'核验结论'};
const auditValue=value=>value==null||value===''?'--':Array.isArray(value)?value.map(auditValue).join('、'):typeof value==='object'?'已记录详情':readableLabel(value,String(value));
function auditDetailBlock(title,data){const entries=Object.entries(data||{}).filter(([,value])=>value!=null&&value!=='');if(!entries.length)return '';return `<section class="ops-card"><h3>${esc(title)}</h3><div class="ops-detail-grid">${entries.map(([key,value])=>`<div class="ops-detail"><small>${esc(AUDIT_FIELD_LABEL[key]||'相关信息')}</small><b>${esc(auditValue(value))}</b></div>`).join('')}</div></section>`}
function auditDetail(event){const operationCode=recordCode(event.request_id||event.id,'OP');modal('操作详情',`<div class="ops-detail-grid">${[['操作人',event.actor_name||'系统自动处理'],['操作时间',fmt(event.created_at)],['处理事项',auditAction(event.action)],['相关记录',`${auditResource(event.resource_type)} · ${recordCode(event.resource_id,'业务')}`],['加盟商',recordCode(event.company_id,'加盟商')],['操作结果','已完成'],['操作编号',operationCode]].map(([name,value])=>`<div class="ops-detail"><small>${esc(name)}</small><b>${esc(value)}</b></div>`).join('')}</div>${auditDetailBlock('变更前',event.before)}${auditDetailBlock('变更后',event.after)}${auditDetailBlock('处理说明',event.metadata)}<div class="ops-actions"><button class="ops-btn primary" id="copy-operation-code">复制操作编号</button></div>`,()=>{document.querySelector('#copy-operation-code').onclick=async()=>{try{await navigator.clipboard.writeText(operationCode);toast('操作编号已复制')}catch{toast('浏览器不支持自动复制，请手动复制',true)}}})}
async function audit(){const business=S.id||'';const [d,failedOutbox]=await Promise.all([api(`/v1.2/audit-events${qs({page:S.page,page_size:50,business_id:business})}`),can('notification.retry')?api('/notifications/outbox/failed'):Promise.resolve([])]);const events=d.items||[];const rows=events.map(x=>`<tr data-audit-row="${esc(x.id)}"><td>${fmt(x.created_at)}</td><td><b>${esc(x.actor_name||'系统自动处理')}</b><br><small>${esc(x.actor_user_id?recordCode(x.actor_user_id,'账号'):'系统任务')}</small></td><td><b>${esc(auditAction(x.action))}</b><br><small>${esc(auditResource(x.resource_type))} · ${esc(recordCode(x.resource_id,'业务'))}</small></td><td>${badge('APPROVED')}<br><small>已完成</small></td><td>${esc(recordCode(x.request_id||x.id,'OP'))}</td><td><button class="ops-btn" data-audit-detail="${esc(x.id)}">查看详情</button></td></tr>`);const failureRows=(failedOutbox||[]).map(item=>`<tr data-outbox-detail="${esc(item.id)}"><td>${esc(notificationEventLabel(item.event_type))}</td><td>${esc(notificationStatusLabel(item.status))}</td><td>${esc(notificationFailureAdvice(item))}</td><td>${item.attempts||0} 次</td><td>${fmt(item.created_at)}</td><td><button class="ops-btn primary" data-outbox-retry="${esc(item.id)}">重新发送</button></td></tr>`);const failurePanel=can('notification.retry')?`<section class="ops-card"><div class="ops-card-head"><div><h2>通知发送异常</h2><p>仅显示需要处理的消息；双击某一条可查看详情，重新发送前请先确认接收人和消息模板配置。</p></div></div>${table(['通知内容','当前状态','处理建议','已尝试','创建时间','操作'],failureRows)}</section>`:'';shell(`<div class="ops-filter"><input class="ops-input" id="business" placeholder="输入客资、派发、退回或操作编号" value="${esc(business)}"><button class="ops-btn primary" id="query">查询记录</button><button class="ops-btn gold" id="trace" ${business?'':'disabled'}>查看客资详情</button></div><section class="ops-card"><div class="ops-card-head"><div><h2>操作日志</h2><p>每条记录均可查看谁在何时处理了哪项业务；双击表格行或点击详情均可展开。操作编号仅用于查询与追溯，不可编辑。</p></div></div>${table(['时间','操作人','处理事项','操作结果','操作编号','详情'],rows)}${pager(d)}</section>${failurePanel}`);bindPager(d,audit);document.querySelector('#query').onclick=()=>go('audit',document.querySelector('#business').value.trim());document.querySelector('#trace').onclick=()=>go('trace',document.querySelector('#business').value.trim());const eventById=Object.fromEntries(events.map(event=>[event.id,event]));document.querySelectorAll('[data-audit-detail]').forEach(button=>button.onclick=()=>auditDetail(eventById[button.dataset.auditDetail]));document.querySelectorAll('[data-audit-row]').forEach(row=>row.ondblclick=()=>auditDetail(eventById[row.dataset.auditRow]));const failedById=Object.fromEntries((failedOutbox||[]).map(item=>[item.id,item]));document.querySelectorAll('[data-outbox-detail]').forEach(row=>row.ondblclick=()=>notificationFailureDetail(failedById[row.dataset.outboxDetail]));document.querySelectorAll('[data-outbox-retry]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await retryOutbox(button.dataset.outboxRetry)}catch(error){button.disabled=false;toast(error.message,true)}})}
function latestItem(items){return items?.length?items[items.length-1]:null}
function traceStep(title,status,detail,iconName){return `<article class="ops-trace-step"><i aria-hidden="true">${icon(iconName)}</i><div><small>${esc(title)}</small><b>${esc(status||'未涉及')}</b><p>${esc(detail||'')}</p></div></article>`}
function traceNextStep(lead,assignment,task,returnRequest){
  if(returnRequest&&['DRAFT','SUBMITTED','VERIFYING','REVIEWING','NEED_MORE_EVIDENCE'].includes(returnRequest.status))return '等待退回审核完成';
  if(task&&['PENDING','ASSIGNED','IN_PROGRESS','SUBMITTED'].includes(task.status))return task.status==='SUBMITTED'?'等待运营确认核验结论':'等待电销完成电话核验';
  if(lead?.status==='DRAFT'||lead?.review_status==='DRAFT')return '等待补齐客户信息后提交初审';
  if(lead?.status==='READY_DISPATCH')return '等待运营派发给合适的加盟商';
  if(assignment?.status==='PENDING_CLAIM'||assignment?.status==='WAITING_CLAIM')return '等待加盟商领取';
  if(assignment?.status==='CLAIMED'||assignment?.status==='FOLLOWING')return '等待加盟商更新跟进结果';
  return '本条客资已完成当前环节';
}
function traceTimeline(items){return (items||[]).map(item=>{
  const title=item.kind==='NOTIFICATION'?'发送消息提醒':auditAction(item.action);
  const actor=item.kind==='NOTIFICATION'?'系统提醒':item.actor_name||'系统自动处理';
  return `<article class="ops-trace-event"><time>${esc(fmt(item.at))}</time><i aria-hidden="true"></i><div><b>${esc(title)}</b><small>${esc(actor)}</small>${item.summary?`<p>${esc(item.summary)}</p>`:''}</div></article>`;
}).join('')||'<div class="ops-empty">当前没有可显示的处理记录</div>'}
async function fullTrace(){
  if(!S.id){shell('<section class="ops-card ops-empty">请选择一条客资后查看详情。</section>');return}
  const d=await api(`/v1.2/trace/${encodeURIComponent(S.id)}`);
  const lead=d.lead||{},assignments=d.assignments||[],returns=d.returns||[],tasks=d.verification_tasks||[],followups=d.followups||[],rewards=d.supplier_rewards||[],ledgers=d.points_ledgers||[];
  const assignment=latestItem(assignments),returnRequest=latestItem(returns),task=latestItem(tasks),followup=latestItem(followups),reward=latestItem(rewards);
  const evidence=returns.flatMap(item=>item.evidences||[]);
  const steps=[
    traceStep('客资提交',label(lead.status),lead.submitted_at?`提交于 ${fmt(lead.submitted_at)}`:`录入于 ${fmt(lead.created_at)}`,'file-text'),
    traceStep('初审确认',label(lead.review_status),lead.review_note||'等待运营确认资料是否完整','user-check'),
    traceStep('电话核验',task?label(task.status):'未安排',task?`${task.assignee_name||'待分配'}${task.conclusion?`，结论：${label(task.conclusion)}`:''}`:'本条客资暂不需要电话核验','phone'),
    traceStep('派发领取',assignment?label(assignment.status):'待派发',assignment?`${assignment.receiver_company_name||assignment.company_name||'待确定加盟商'}${assignment.claimed_at?`，领取于 ${fmt(assignment.claimed_at)}`:''}`:'等待运营选择接收加盟商','hand-claim'),
    traceStep('跟进反馈',followup?label(followup.status):'暂无反馈',followup?.note||'加盟商领取后会在这里记录跟进结果','file-text'),
    traceStep('退回审核',returnRequest?label(returnRequest.status):'未发起',returnRequest?`${label(returnRequest.reason_code)}${returnRequest.final_decision_reason?`：${returnRequest.final_decision_reason}`:''}`:'如客户信息无效，加盟商可提交材料申请退回','rotate-ccw'),
  ];
  const pointsText=reward?`${reward.reward_points||0} 积分${reward.status?`，${label(reward.status)}`:''}`:'本条客资暂未产生供资奖励';
  const summary=`<section class="ops-card ops-trace-customer"><div class="ops-card-head"><div><h2>${esc(lead.customer_name||'客资详情')}</h2><p>${esc(recordCode(lead.id||d.business_id,'KZ'))} · ${esc(lead.city||'待补充地区')} ${esc(lead.district||'')}</p></div><div>${badge(lead.status)}</div></div><div class="ops-detail-grid">${[['客资来源',label(lead.source_kind)],['联系电话',lead.phone_masked],['提交人',lead.submitter_name],['所在地',`${lead.city||''} ${lead.district||''}`],['初审结果',label(lead.review_status)],['当前处理',traceNextStep(lead,assignment,task,returnRequest)]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'待确认')}</b></div>`).join('')}</div><div class="ops-trace-need"><small>客户需求</small><p>${esc(lead.need_summary||'暂未填写客户需求')}</p></div></section>`;
  const main=`<div class="ops-trace-main">${summary}<section class="ops-card"><div class="ops-card-head"><div><h2>处理进度</h2><p>按实际发生顺序展示，未涉及的环节会明确标注。</p></div></div><div class="ops-trace-steps">${steps.join('')}</div></section><section class="ops-card"><div class="ops-card-head"><div><h2>处理记录</h2><p>每次处理都会保留时间、处理人和说明。</p></div></div><div class="ops-trace-timeline">${traceTimeline(d.timeline)}</div></section></div>`;
  const dispatchInfo=assignment?`<div class="ops-detail-grid">${[['派发编号',recordCode(assignment.id,'PF')],['接收加盟商',assignment.receiver_company_name||assignment.company_name],['派发时间',fmt(assignment.assigned_at)],['领取状态',label(assignment.status)],['领取积分',`${assignment.claim_points??assignment.points_price??0} 积分`],['当前跟进',label(assignment.current_follow_status)]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'待确认')}</b></div>`).join('')}</div>`:'<div class="ops-empty">客资尚未派发</div>';
  const returnInfo=returnRequest?`<div class="ops-detail-grid">${[['退回状态',label(returnRequest.status)],['退回原因',label(returnRequest.reason_code)],['申请时间',fmt(returnRequest.submitted_at)],['审核结果',returnRequest.review_note||returnRequest.final_decision_reason||'等待审核'],['返还积分',returnRequest.refund_points==null?'待审核':`${returnRequest.refund_points} 积分`],['核验结论',label(returnRequest.verification?.conclusion)]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'待确认')}</b></div>`).join('')}</div>${evidence.length?`<h3 class="ops-trace-subtitle">申诉证据</h3><div class="ops-detail-grid">${evidenceList(evidence)}</div>`:''}`:'<div class="ops-empty">当前没有退回申请</div>';
  const rewardInfo=`<div class="ops-detail-grid">${[['供资奖励',pointsText],['积分记录',ledgers.length?`${ledgers.length} 笔`:'暂无'],['最近积分变化',ledgers.length?`${ledgers[ledgers.length-1].delta>0?'+':''}${ledgers[ledgers.length-1].delta} 积分`:'--'],['消息提醒',d.notifications?.length?`${d.notifications.length} 条`:'暂无']].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b)}</b></div>`).join('')}</div>`;
  const side=`<aside class="ops-trace-side"><section class="ops-card"><h2>当前处理</h2><div class="ops-trace-current">${badge(returnRequest?.status||task?.status||assignment?.status||lead.status)}<b>${esc(traceNextStep(lead,assignment,task,returnRequest))}</b><p>${esc(task?.assignee_name?`当前由 ${task.assignee_name} 处理`:'请根据当前状态继续处理')}</p></div></section><section class="ops-card"><h2>派发信息</h2>${dispatchInfo}</section><section class="ops-card"><h2>退回审核</h2>${returnInfo}</section><section class="ops-card"><h2>积分与奖励</h2>${rewardInfo}</section></aside>`;
  shell(`<div class="ops-trace-actions"><button class="ops-btn" id="trace-back">返回上一页</button><button class="ops-btn primary" id="trace-log">查看处理日志</button></div><div class="ops-trace-layout">${main}${side}</div>`);
  document.querySelector('#trace-back').onclick=()=>history.length>1?history.back():go('leads');
  document.querySelector('#trace-log').onclick=()=>go('audit',d.business_id);
}
function redirectToAllowedSurface(){
  const roles=new Set(S.me?.roles||[]);
  if(roles.has('SUPER_ADMIN')||roles.has('OPERATION')){location.replace('/admin/v12-operations.html');return true}
  if(roles.has('TELESALES')){location.replace('/h5/call/');return true}
  if(roles.has('FRANCHISE_OWNER')||roles.has('FRANCHISE_EMPLOYEE')){location.replace('/h5/');return true}
  return false;
}
function renderLogin(message=''){
  zsSetSafeHtml(app, `<div class="ops-login-shell"><section class="ops-login-brand"><img src="./logo.png" alt="合家美宅" class="ops-login-logo"><div><span>合家美宅</span><h1>统一工作台</h1><p>客资流转、加盟商协同与经营治理</p></div></section><section class="ops-card ops-login-card"><div class="ops-card-head"><div><h2>平台管理登录</h2><p>使用平台管理员或运营管理员账号登录。</p></div></div>${message?`<div class="ops-notice">${esc(message)}</div>`:''}<form class="ops-form" id="platform-login-form"><div class="ops-field"><label for="username">登录账号</label><input class="ops-input" id="username" autocomplete="username" required></div><div class="ops-field"><label for="password">登录密码</label><input class="ops-input" id="password" type="password" autocomplete="current-password" required></div><button class="ops-btn primary ops-login-submit" id="login-btn" type="submit">登录工作台</button></form></section></div>`);
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
