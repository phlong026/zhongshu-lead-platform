const API='/api/v1',app=document.querySelector('#app'),toastEl=document.querySelector('#toast'),modalRoot=document.querySelector('#modal-root');
const S={me:null,view:'overview',id:'',page:1,companyStatus:'PENDING',companyCapabilityPage:1,companyAreaPage:1,telesalesUsers:null};
const P={overview:['工作台','layout-dashboard',['*','dashboard.business.read','dashboard.operation.read','dashboard.finance.read','lead.manual.manage','return.review']],review:['加盟商初审','user-check',['lead.supplier.review']],dispatch:['人工派发','hand-claim',['lead.dispatch']],companies:['加盟商审核','building',['company.profile.review']],returns:['退回与核验','rotate-ccw',['return.read','return.review','verification.read']],rewards:['奖励管理','award',['reward.read','reward.manage']],audit:['报表与审计','search',['audit.read']]};
const ROLE_HOME_CONTRACT={SUPER_ADMIN:'系统治理',OWNER:'经营总览',LEAD_ENTRY:'录入工作台',OPERATION:'今日运营',TELESALES:'电话核验',FINANCE:'积分财务',RETURN_REVIEWER:'退回审核',FRANCHISE_OWNER:'加盟商工作台'};
const ROLE_HOME_PRIORITY=['SUPER_ADMIN','OWNER','OPERATION','FINANCE','LEAD_ENTRY','RETURN_REVIEWER','TELESALES','FRANCHISE_OWNER'];
const ADMIN_ROLE_HOME_CONTENT={
  SUPER_ADMIN:{title:'系统治理',subtitle:'风险预警、账号角色、加盟商配置、积分规则、工作日历和通知失败集中巡检。',cards:['风险预警','账号角色','加盟商配置','积分规则','工作日历','通知失败','高风险审计']},
  OWNER:{title:'经营总览',subtitle:'查看客资漏斗、领取跟进、退回率、积分充值消耗返还、趋势与异常。',cards:['客资漏斗','派发领取','跟进成交','退回率','积分变化','趋势异常']},
  OPERATION:{title:'今日运营',subtitle:'聚焦待初审、待派发、待分配电销、待终审、加盟商能力和通知异常。',cards:['待初审','待派发','待分配电销','待终审','能力区域待审','通知异常']},
  FINANCE:{title:'积分财务',subtitle:'处理总余额、充值消耗返还、人工入账、积分规则、流水与冲正。',cards:['总余额','充值记录','消耗返还','人工入账','积分规则','流水冲正']},
  LEAD_ENTRY:{title:'录入工作台',subtitle:'处理新建录入、继续录入、待补信息、疑似重复和最近提交。',cards:['新建录入','继续录入','待补信息','疑似重复','最近提交']},
  RETURN_REVIEWER:{title:'退回审核',subtitle:'处理待终审、待补证、已完成核验、截止提醒和证据摘要。',cards:['待终审','待补证','已完成核验','截止提醒','证据摘要']},
};
const SYSTEM_LINKS=[
  {key:'users',label:'账号与角色',icon:'users',href:'./index.html#/users',permissions:['*']},
  {key:'companies',label:'加盟商公司',icon:'building',href:'./index.html#/companies',permissions:['company.read']},
  {key:'points',label:'积分档位与定价',icon:'coins',href:'./index.html#/points',permissions:['points.read','points.package.manage']},
  {key:'recharge',label:'人工充值',icon:'plus',href:'./index.html#/recharge',permissions:['points.recharge']},
  {key:'ledgers',label:'积分流水',icon:'receipt',href:'./index.html#/ledgers',permissions:['points.read']},
  {key:'calendar',label:'工作日历',icon:'calendar',href:'./index.html#/calendar',permissions:['calendar.read']},
  {key:'configs',label:'规则配置',icon:'settings',href:'./index.html#/configs',permissions:['*']},
];
const L={DRAFT:'待完善',IMPORTED:'待补信息',IMPORT_ERROR:'导入异常',DUPLICATE_REVIEW:'疑似重复',PENDING:'待审核',PENDING_REVIEW:'待初审',READY_DISPATCH:'待派发',PENDING_CLAIM:'待领取',CLAIMED:'已领取',SUBMITTED:'已提交',VERIFYING:'核验中',REVIEWING:'待终审',NEED_MORE_EVIDENCE:'待补证',APPROVED:'已通过',REJECTED:'已驳回',OBSERVING:'观察期',FROZEN:'已冻结',SETTLED:'已结算',CANCELLED:'已取消',REVERSED:'已撤销',ASSIGNED:'待处理',IN_PROGRESS:'核验中',CLEAR:'无重复',DUPLICATE:'疑似重复',PLATFORM_MANUAL:'平台录入',SUPPLIER_H5:'加盟商提交',EMPTY_NUMBER:'空号或停机',OUT_OF_SERVICE_REGION:'超出服务区域',DUPLICATE_TO_RECEIVER:'接收方重复客户',NON_HOUSING_CONSULTATION:'非建房装修咨询',CONNECTED:'已接通',NO_ANSWER:'无人接听',OUT_OF_SERVICE:'停机',WRONG_PERSON:'非本人',REFUSED:'拒接或拒访',OTHER:'其他',SUPPORT_RETURN:'支持退回',DOES_NOT_SUPPORT_RETURN:'不支持退回',INCONCLUSIVE:'信息不足'};
const EVIDENCE_LABEL={CHAT_SCREENSHOT:'沟通截图',CALL_RECORDING:'通话录音'};
const AUDIT_ACTION_LABEL={AUTH_LOGIN:'登录账号',AUTH_LOGOUT:'退出账号',FOLLOWUP_CREATE:'记录客户跟进',WECHAT_OAUTH_START_FAILED:'微信授权未完成',V12_COMPANY_CAPABILITY_REQUEST:'提交加盟商能力申请',V12_PLATFORM_LEAD_DRAFT_CREATE:'新建平台客资草稿',V12_PLATFORM_LEAD_DRAFT_UPDATE:'更新平台客资草稿',V12_PLATFORM_LEAD_SUBMIT:'提交平台客资',V12_SUPPLIER_LEAD_DRAFT_CREATE:'新建加盟商客资草稿',V12_SUPPLIER_LEAD_DRAFT_UPDATE:'更新加盟商客资草稿',V12_SUPPLIER_LEAD_SUBMIT:'提交加盟商客资',V12_SUPPLIER_LEAD_REVIEW:'初审加盟商客资',V12_DEDUP_OVERRIDE:'确认客资不重复',V12_MANUAL_DISPATCH:'人工派发客资',V12_ASSIGNMENT_CLAIM:'领取客资',V12_RETURN_DRAFT_SAVE:'保存退回草稿',V12_RETURN_EVIDENCE_UPLOAD:'上传申诉证据',V12_RETURN_EVIDENCE_READ:'查看申诉证据',V12_RETURN_SUBMIT:'提交退回申诉',V12_RETURN_VERIFY_ASSIGN:'分配电话核验',V12_RETURN_VERIFY_CLAIM:'领取电话核验',V12_RETURN_VERIFY_DIAL:'拨打核验电话',V12_RETURN_VERIFY_SUBMIT:'提交电话核验',V12_RETURN_FINAL_REVIEW:'完成退回终审',V12_SUPPLIER_REWARD_RULE_CREATE:'新建奖励规则',V12_SUPPLIER_REWARD_RULE_PUBLISH:'发布奖励规则',V12_SUPPLIER_REWARD_SETTLE:'结算供客奖励',V12_SUPPLIER_REWARD_SETTLE_DUE:'批量结算到期奖励',V12_SUPPLIER_REWARD_REVERSE:'撤销供客奖励'};
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
function primaryRole(){const roles=new Set(S.me?.roles||[]);return ROLE_HOME_PRIORITY.find(role=>roles.has(role))||'OWNER'}
function nav(){return Object.entries(P).filter(([,m])=>allowed(m)).map(([k,m])=>`<button class="${S.view===k?'active':''}" data-view="${k}"><span>${icon(m[1])}</span><span>${m[0]}</span></button>`).join('')}
function visibleSystemLinks(){return SYSTEM_LINKS.filter(link=>link.permissions.some(can))}
function systemNav(links){return links.map(link=>`<a data-system-setting="${link.key}" href="${link.href}" title="打开${link.label}"><span>${icon(link.icon)}</span><span>${link.label}</span></a>`).join('')}
function shell(body){
  const meta=P[S.view]||P.overview;
  const roleHome=ADMIN_ROLE_HOME_CONTENT[primaryRole()];
  const pageTitle=S.view==='overview'&&roleHome?roleHome.title:meta[0];
  const pageSubtitle=S.view==='overview'&&roleHome?'角色专属首页':'客资运营管理';
  const systemLinks=visibleSystemLinks();
  const systemShortcut=systemLinks[0];
  const systemSection=systemLinks.length?`<div class="ops-menu-label">系统设置</div><nav class="ops-menu ops-system-menu">${systemNav(systemLinks)}</nav>`:'';
  const shortcut=systemShortcut?`<a class="ops-btn" data-system-settings-shortcut href="${systemShortcut.href}">${icon('settings')}系统设置</a>`:'';
  zsSetSafeHtml(app, `<div class="ops-shell"><aside class="ops-side"><div class="ops-brand"><img class="ops-logo" src="./logo.png" alt="合家美宅"><div><strong>合家美宅</strong><small>客资运营台</small></div></div><div class="ops-menu-label">业务运营</div><nav class="ops-menu">${nav()}</nav>${systemSection}<div class="ops-side-foot">${esc(S.me?.display_name||'')}</div></aside><section class="ops-main"><header class="ops-top"><div class="ops-title"><h1>${esc(pageTitle)}</h1><p>${esc(pageSubtitle)}</p></div><div class="ops-top-actions">${shortcut}<button class="ops-btn" id="logout" type="button">${icon('log-out')}退出</button><button class="ops-btn primary" id="refresh">${icon('rotate-ccw')}刷新</button></div></header><main class="ops-content">${body}</main></section></div>`);
  document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>go(button.dataset.view));
  document.querySelector('#refresh').onclick=render;
  document.querySelector('#logout').onclick=async()=>{await api('/auth/logout',{method:'POST'}).catch(()=>{});location.replace('/admin/index.html')};
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
function statusSummary(data){return `<div class="ops-detail-grid">${Object.entries(data||{}).map(([status,count])=>`<div class="ops-detail"><small>${esc(label(status))}</small><b>${Number(count||0)}</b></div>`).join('')||'<div class="ops-empty">暂无状态数据</div>'}</div>`}
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
async function render(){shell('<div class="ops-loading">加载中…</div>');try{await ({overview,review,dispatch,companies,returns,rewards,audit}[S.view]||overview)()}catch(e){shell(`<div class="ops-error">${esc(e.message)}</div>`);toast(e.message,true)}}
const totalOf=values=>Object.values(values||{}).reduce((sum,value)=>sum+Number(value||0),0);
const countStatus=(items,statuses)=>items.filter(item=>statuses.includes(item.status)).length;
function roleMetricCards(cards){return `<div class="ops-grid ops-role-metrics">${cards.map(([name,value,iconName,href])=>{const content=`<i>${icon(iconName)}</i><small>${esc(name)}</small><b>${esc(value??0)}</b>`;return href?`<a class="ops-kpi" href="${href}">${content}</a>`:`<div class="ops-kpi">${content}</div>`}).join('')}</div>`}
function roleHome(content,cards,body=''){shell(`<section class="ops-role-hero"><div><span>今日工作面</span><h2>${esc(content.title)}</h2><p>${esc(content.subtitle)}</p></div><div class="ops-role-mark">${icon('layout-dashboard')}</div></section>${roleMetricCards(cards)}${body}`)}
async function leadEntryHome(){
  const data=await api('/leads/staging?page=1&page_size=20');
  const items=data.items||[];
  const rows=items.slice(0,8).map(item=>`<tr><td><b>${esc(item.customer_name||'待补姓名')}</b></td><td>${esc(item.city||'地区待补')}</td><td>${badge(item.status)}</td><td>${fmt(item.imported_at||item.created_at)}</td><td><a class="ops-btn" href="./v12-leads.html?id=${encodeURIComponent(item.id)}">继续处理</a></td></tr>`);
  roleHome(ADMIN_ROLE_HOME_CONTENT.LEAD_ENTRY,[
    ['新建录入','开始','plus','./v12-leads.html'],
    ['继续录入',data.total||0,'inbox','./v12-leads.html'],
    ['待补信息',countStatus(items,['IMPORTED','IMPORT_ERROR']),'alert-triangle','./v12-leads.html'],
    ['疑似重复',countStatus(items,['DUPLICATE_REVIEW']),'alert-triangle','./v12-leads.html'],
  ],`<section class="ops-card"><div class="ops-card-head"><div><h2>最近提交</h2><p>优先补齐信息不完整或需要复核的客资。</p></div><a class="ops-btn primary" href="./v12-leads.html">进入录入台</a></div>${table(['客户','地区','状态','更新时间','操作'],rows)}</section>`);
}
async function returnReviewerHome(){
  const data=await api('/v1.2/returns?page=1&page_size=20');
  const items=data.items||[];
  const rows=items.slice(0,8).map(item=>`<tr><td>${esc(recordCode(item.id,'TH'))}</td><td>${esc(label(item.reason_code))}</td><td>${badge(item.status)}</td><td>${fmt(item.submitted_at||item.created_at)}</td><td><button class="ops-btn" data-return-home="${esc(item.id)}">查看审核</button></td></tr>`);
  roleHome(ADMIN_ROLE_HOME_CONTENT.RETURN_REVIEWER,[
    ['待终审',countStatus(items,['REVIEWING']),'clipboard-check'],
    ['待补证',countStatus(items,['NEED_MORE_EVIDENCE']),'file-text'],
    ['已完成核验',countStatus(items,['APPROVED','REJECTED']),'user-check'],
    ['截止提醒',items.filter(item=>item.appeal_deadline_at).length,'calendar'],
  ],`<section class="ops-card"><div class="ops-card-head"><div><h2>退回审核队列</h2><p>同屏核对申诉说明、证据、电话核验和处理影响。</p></div></div>${table(['申诉编号','退回原因','状态','提交时间','操作'],rows)}</section>`);
  document.querySelectorAll('[data-return-home]').forEach(button=>button.onclick=()=>returnDetail(button.dataset.returnHome));
}
function platformRoleHome(role,report,summary,alerts){
  const business=summary.business||{},finance=summary.finance||{},alertTotal=totalOf(alerts);
  let cards=[];
  if(role==='SUPER_ADMIN')cards=[['风险预警',alertTotal,'alert-triangle'],['账号角色','管理','users','./index.html#/users'],['加盟商配置',business.active_companies||0,'building','./index.html#/companies'],['积分规则','查看','coins','./index.html#/points'],['工作日历','查看','calendar','./index.html#/calendar'],['通知失败',alerts.failed_notifications||0,'bell'],['高风险审计','查看','search']];
  else if(role==='OWNER')cards=[['客资漏斗',business.total_leads||report.leads.total,'list'],['派发领取',business.claimed_total||0,'hand-claim'],['跟进率',`${business.followup_rate||0}%`,'phone'],['成交率',`${business.conversion_rate||0}%`,'award'],['退回申诉',report.returns.total,'rotate-ccw'],['积分变化',report.points_ledger?.net_delta??0,'activity'],['异常提醒',alertTotal,'alert-triangle']];
  else if(role==='FINANCE')cards=[['总余额',finance.points_balance_total||0,'coins','./index.html#/ledgers'],['充值积分',finance.points_recharged_total||0,'plus','./index.html#/recharge'],['消耗积分',finance.points_consumed_total||0,'receipt','./index.html#/ledgers'],['返还积分',finance.points_refunded_total||0,'rotate-ccw','./index.html#/ledgers'],['积分流水',report.points_ledger?.count||0,'list','./index.html#/ledgers'],['净积分变化',report.points_ledger?.net_delta||0,'activity','./index.html#/ledgers']];
  else cards=[['待初审',report.leads.by_status?.PENDING_REVIEW||0,'user-check'],['待派发',report.leads.by_status?.READY_DISPATCH||0,'hand-claim'],['待分配电销',report.returns.by_status?.VERIFYING||0,'phone'],['待终审',report.returns.by_status?.REVIEWING||0,'clipboard-check'],['能力区域待审','进入审核','building'],['通知异常',alerts.failed_notifications||0,'bell']];
  const aggregate=role==='FINANCE'?'':`<section class="ops-card"><div class="ops-card-head"><div><h2>业务状态</h2><p>只展示当前岗位需要处理的汇总信息。</p></div></div><div class="ops-summary-columns"><div><h3>客资</h3>${statusSummary(report.leads.by_status)}</div><div><h3>派发</h3>${statusSummary(report.assignments.by_status)}</div><div><h3>退回</h3>${statusSummary(report.returns.by_status)}</div></div></section>`;
  roleHome(ADMIN_ROLE_HOME_CONTENT[role]||ADMIN_ROLE_HOME_CONTENT.OWNER,cards,aggregate);
}
async function overview(){
  const role=primaryRole();
  if(role==='LEAD_ENTRY')return leadEntryHome();
  if(role==='RETURN_REVIEWER')return returnReviewerHome();
  const [report,summary,alerts]=await Promise.all([api('/v1.2/reports/overview'),api('/dashboard/summary'),api('/dashboard/alerts')]);
  platformRoleHome(role,report,summary,alerts);
}
async function review(){const d=await api(`/v1.2/admin/supplier-leads${qs({page:S.page,page_size:20})}`);const rows=(d.items||[]).map(x=>`<tr><td><b>${esc(x.customer_name)}</b><br>${esc(x.phone_masked||'--')}</td><td>${esc(x.city||'--')} ${esc(x.district||'')}</td><td>${badge(x.status)} ${badge(x.review_status)}</td><td>${esc(label(x.duplicate_status))}</td><td>${fmt(x.submitted_at)}</td><td><button class="ops-btn" data-detail="${x.id}">详情</button>${x.review_status==='PENDING'?` <button class="ops-btn primary" data-review="${x.id}:APPROVE">通过</button> <button class="ops-btn danger" data-review="${x.id}:REJECT">驳回</button>`:''}</td></tr>`);shell(`<section class="ops-card"><div class="ops-card-head"><div><h2>加盟商客资初审</h2><p>列表只展示脱敏手机号。</p></div></div>${table(['客户','区域','状态','去重','提交时间','操作'],rows)}${pager(d)}</section>`);bindPager(d,review);document.querySelectorAll('[data-detail]').forEach(b=>b.onclick=()=>reviewDetail(b.dataset.detail));document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>{const [id,decision]=b.dataset.review.split(':');reviewAction(id,decision)});if(S.id){const id=S.id;S.id='';reviewDetail(id)}}
async function reviewDetail(id){const x=await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(id)}`);modal('客资初审详情',`<div class="ops-detail-grid">${[['客资编号',recordCode(x.id,'KZ')],['客户',x.customer_name],['手机号',x.phone_masked],['处理状态',label(x.status)],['初审结果',label(x.review_status)],['重复检查',label(x.duplicate_status)],['服务地区',`${x.city||''} ${x.district||''}`]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>客户需求</h3><p class="ops-muted">${esc(x.need_summary||'暂无说明')}</p></section><button class="ops-btn" id="trace">查看完整记录</button>`,()=>document.querySelector('#trace').onclick=()=>{closeModal();go('audit',id)})}
function reviewAction(id,decision){actionForm({title:decision==='REJECT'?'驳回客资':'通过客资初审',message:'提交后将记录操作人和处理说明。',labelText:'初审说明',required:decision==='REJECT',minLength:2,submitLabel:decision==='REJECT'?'确认驳回':'确认通过',danger:decision==='REJECT'},async note=>{await api(`/v1.2/admin/supplier-leads/${encodeURIComponent(id)}/review`,{method:'POST',body:JSON.stringify({decision,note:note||null})});toast('初审结果已提交');await review()})}
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
  const capabilityRows=(capabilities.items||[]).map(item=>`<tr><td><b>${esc(item.company_name)}</b><br><small>${esc(recordCode(item.company_id,'加盟商'))}</small></td><td>${esc(CAPABILITY_LABEL[item.capability_code]||readableLabel(item.capability_code,'其他能力'))}</td><td>${badge(item.review_status)}<br><small>${item.active?'已启用':'未启用'}</small></td><td>${esc(cleanProfileNote(item.review_note)||'--')}</td><td>${fmt(item.reviewed_at)}</td><td>${capabilityReviewActions(item)}</td></tr>`);
  const areaRows=(areas.items||[]).map(item=>{const removal=String(item.review_note||'').startsWith('[REMOVE_REQUEST]');return `<tr><td><b>${esc(item.company_name)}</b><br><small>${esc(recordCode(item.company_id,'加盟商'))}</small></td><td>${esc(item.region_name||recordCode(item.region_code,'区域'))}<br><small>${esc(item.is_primary_city?'主要城市':readableLabel(item.region_level,'服务区域'))}</small></td><td>${badge(item.review_status)}<br><small>${removal&&item.active?'待移除，当前仍生效':item.active?'已生效':'未生效'}</small></td><td>${esc(cleanProfileNote(item.review_note)||'--')}</td><td>${fmt(item.reviewed_at)}</td><td>${areaReviewActions(item)}</td></tr>`});
  shell(`<section class="ops-card company-review"><div class="ops-card-head"><div><h2>加盟商能力与服务区域审核申请</h2><p>供客与接收能力独立审核；区域移除申请在批准前继续保持原服务资格。</p></div><select class="ops-input" id="company-review-status" style="width:auto"><option value="PENDING" ${S.companyStatus==='PENDING'?'selected':''}>待审核</option><option value="APPROVED" ${S.companyStatus==='APPROVED'?'selected':''}>已通过</option><option value="REJECTED" ${S.companyStatus==='REJECTED'?'selected':''}>已驳回</option></select></div><h3>公司能力（${capabilities.total||0}）</h3>${table(['加盟商','能力','状态','审核说明','审核时间','操作'],capabilityRows)}${companyQueuePager(capabilities,'capability',S.companyCapabilityPage)}</section><section class="ops-card company-review"><h3>服务区域（${areas.total||0}）</h3>${table(['加盟商','区域','状态','审核说明','审核时间','操作'],areaRows)}${companyQueuePager(areas,'area',S.companyAreaPage)}</section>`);
  document.querySelector('#company-review-status').onchange=event=>{S.companyStatus=event.target.value;S.companyCapabilityPage=1;S.companyAreaPage=1;companies()};
  bindCompanyQueuePager(capabilities,'capability','companyCapabilityPage');
  bindCompanyQueuePager(areas,'area','companyAreaPage');
  document.querySelectorAll('[data-cap-decision]').forEach(button=>button.onclick=()=>reviewCompanyCapability(button));
  document.querySelectorAll('[data-area-decision]').forEach(button=>button.onclick=()=>reviewCompanyArea(button));
}
async function reviewCompanyCapability(button){
  const decision=button.dataset.capDecision;
  actionForm({title:decision==='REJECT'?'驳回或停用公司能力':'通过公司能力',message:'能力状态会影响加盟商能否供应或接收客资。',labelText:'审核说明',required:decision==='REJECT',minLength:2,submitLabel:decision==='REJECT'?'确认驳回或停用':'确认通过',danger:decision==='REJECT'},async note=>{await api(`/v1.2/admin/companies/${encodeURIComponent(button.dataset.capCompany)}/capabilities/${encodeURIComponent(button.dataset.capCode)}/review`,{method:'POST',body:JSON.stringify({decision,note:note||null})});toast('公司能力审核已完成');await companies()});
}
async function reviewCompanyArea(button){
  const decision=button.dataset.areaDecision;
  actionForm({title:decision==='REJECT'?'驳回服务区域':'通过服务区域',message:'移除申请在审核通过前仍保持原服务资格。',labelText:'审核说明',required:decision==='REJECT',minLength:2,submitLabel:decision==='REJECT'?'确认驳回':'确认通过',danger:decision==='REJECT'},async note=>{await api(`/v1.2/admin/service-areas/${encodeURIComponent(button.dataset.areaId)}/review`,{method:'POST',body:JSON.stringify({decision,note:note||null})});toast('服务区域审核已完成');await companies()});
}
async function dispatch(){const d=await api(`/v1.2/dispatch-pool${qs({page:S.page,page_size:20})}`);const rows=(d.items||[]).map(x=>`<tr><td><b>${esc(x.customer_name)}</b><br>${esc(x.phone_masked||'--')}</td><td>${esc(x.city||'--')} ${esc(x.district||'')}</td><td>${esc(label(x.source_kind))}</td><td>${esc(x.need_summary||'--')}</td><td><button class="ops-btn primary" data-candidate="${x.id}">选择接收公司</button></td></tr>`);shell(`<section class="ops-card"><h2>待人工派发池</h2>${table(['客户','服务地区','客资来源','客户需求','操作'],rows)}${pager(d)}</section>`);bindPager(d,dispatch);document.querySelectorAll('[data-candidate]').forEach(b=>b.onclick=()=>candidates(b.dataset.candidate));if(S.id){const id=S.id;S.id='';candidates(id)}}
async function candidates(leadId){const d=await api(`/v1.2/dispatch-pool/${encodeURIComponent(leadId)}/candidates`);const rows=(d.candidates||[]).map(x=>`<tr><td>${esc(x.company_name)}</td><td>${x.eligible?badge('APPROVED'):badge('REJECTED')}</td><td>${x.points_price}</td><td>${x.points_available??'按权限隐藏'}</td><td>${esc(candidateReasons(x.exclusion_reasons))}</td><td>${x.eligible?`<button class="ops-btn primary" data-dispatch="${x.company_id}">派发</button>`:'--'}</td></tr>`);modal('选择接收公司',table(['接收公司','是否可派','所需积分','可用积分','判断说明','操作'],rows),()=>document.querySelectorAll('[data-dispatch]').forEach(b=>b.onclick=()=>dispatchOne(leadId,b.dataset.dispatch)))}
function dispatchOne(leadId,companyId){actionForm({title:'确认人工派发',message:'请再次核对接收公司。提交后会生成派发单并记录审计。',labelText:'派发备注',submitLabel:'确认派发'},async note=>{await api(`/v1.2/dispatch-pool/${encodeURIComponent(leadId)}/dispatch`,{method:'POST',body:JSON.stringify({company_id:companyId,idempotency_key:`dispatch-${crypto.randomUUID()}`,note:note||null})});toast('客资已派发');await dispatch()})}
async function returns(){const [d,t]=await Promise.all([api(`/v1.2/returns${qs({page:S.page,page_size:20})}`),can('verification.read')?api('/v1.2/return-verifications/tasks?page=1&page_size=100'):Promise.resolve({items:[]})]);if(can('verification.read'))await loadTelesalesUsers();const rows=(d.items||[]).map(x=>`<tr><td>${esc(recordCode(x.id,'TH'))}<br><small>派发编号 ${esc(recordCode(x.assignment_id,'PF'))}</small></td><td>${esc(label(x.reason_code))}</td><td>${badge(x.status)}</td><td>${fmt(x.submitted_at||x.created_at)}</td><td><button class="ops-btn" data-return="${x.id}">查看与审核</button></td></tr>`);const tasks=(t.items||[]).map(x=>{const r=x.return_request||{},lead=x.lead||{};return `<tr><td><b>${esc(lead.customer_name||'待核验客户')}</b><br><small>${esc(lead.phone_masked||'--')}</small></td><td>${verificationTaskBadge(x)}</td><td>${esc(telesalesName(x.assignee_user_id))}</td><td>${esc(label(r.reason_code))}</td><td><button class="ops-btn" data-task="${x.id}">查看</button> <button class="ops-btn" data-assign="${x.id}">${x.assignee_user_id?'重新分配':'分配人员'}</button></td></tr>`});shell(`<section class="ops-card"><h2>退回申诉</h2>${table(['退回编号','退回原因','处理状态','申诉时间','操作'],rows)}${pager(d)}</section>${can('verification.read')?`<section class="ops-card"><h2>电话核验任务</h2><p>仅在加盟商发起退回申诉后进行电话核验。</p>${table(['客户','状态','核验人员','退回原因','操作'],tasks)}</section>`:''}`);bindPager(d,returns);document.querySelectorAll('[data-return]').forEach(b=>b.onclick=()=>returnDetail(b.dataset.return));document.querySelectorAll('[data-task]').forEach(b=>b.onclick=()=>taskDetail(b.dataset.task));document.querySelectorAll('[data-assign]').forEach(b=>b.onclick=()=>assignTask(b.dataset.assign));if(S.id){const id=S.id;S.id='';returnDetail(id)}}
async function returnDetail(id){const x=await api(`/v1.2/returns/${encodeURIComponent(id)}`);if(can('verification.read'))await loadTelesalesUsers();const verification=x.verification||{};modal('退回申诉详情',`<div class="ops-detail-grid">${[['退回编号',recordCode(x.id,'TH')],['派发编号',recordCode(x.assignment_id,'PF')],['处理状态',label(x.status)],['退回原因',label(x.reason_code)],['核验人员',telesalesName(verification.assignee_user_id)],['核验状态',label(verification.status)],['申诉截止',fmt(x.appeal_deadline_at)],['终审说明',x.final_decision_reason]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>申诉说明</h3><p>${esc(x.description||'暂无说明')}</p></section><section class="ops-card"><h3>申诉证据</h3><div class="ops-detail-grid">${evidenceList(x.evidences)}</div></section>${can('return.review')&&['REVIEWING','NEED_MORE_EVIDENCE'].includes(x.status)?'<div class="ops-actions"><button class="ops-btn primary" data-final="APPROVE">通过退回</button><button class="ops-btn danger" data-final="REJECT">驳回申诉</button><button class="ops-btn" data-final="NEED_MORE">要求补充证据</button></div>':''}`,()=>document.querySelectorAll('[data-final]').forEach(b=>b.onclick=()=>finalReview(id,b.dataset.final)))}
function finalReview(id,decision){const actionLabel={APPROVE:'通过退回',REJECT:'驳回申诉',NEED_MORE:'要求补充证据'}[decision]||'提交终审';actionForm({title:actionLabel,message:'终审会影响积分返还与申诉状态，请写明判断依据。',labelText:'终审说明',required:true,minLength:2,submitLabel:`确认${actionLabel}`,danger:decision==='REJECT'},async note=>{await api(`/v1.2/returns/${encodeURIComponent(id)}/final-review`,{method:'POST',body:JSON.stringify({decision,note})});toast('终审完成');await returns()})}
async function taskDetail(id){const x=await api(`/v1.2/return-verifications/tasks/${encodeURIComponent(id)}`);await loadTelesalesUsers();const r=x.return_request||{},lead=x.lead||{},evidenceTotal=Object.values(r.evidence_summary||{}).reduce((sum,count)=>sum+Number(count||0),0);modal('电话核验详情',`<div class="ops-detail-grid">${[['客户',lead.customer_name],['联系电话',lead.phone||lead.phone_masked],['服务地区',`${lead.city||''} ${lead.district||''}`],['任务状态',verificationTaskLabel(x)],['核验人员',telesalesName(x.assignee_user_id)],['退回原因',label(r.reason_code)],['证据数量',`${evidenceTotal} 份`],['处理期限',fmt(r.appeal_deadline_at)],['联系结果',label(x.contact_result)],['核验结论',label(x.conclusion)]].map(([a,b])=>`<div class="ops-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><section class="ops-card"><h3>申诉说明</h3><p>${esc(r.description||'暂无说明')}</p></section>`)}
async function assignTask(id){try{const users=await loadTelesalesUsers();const options=users.map(user=>`<option value="${esc(user.id)}">${esc(user.display_name||user.username)}${user.username?` · ${esc(user.username)}`:''}</option>`).join('');modal('选择电销人员',users.length?`<div class="ops-field"><label for="telesales-assignee">电销人员</label><select class="ops-input" id="telesales-assignee">${options}</select></div><div class="ops-actions"><button class="ops-btn primary" id="confirm-assignment">确认分配</button></div>`:'<div class="ops-empty">暂无可分配的电销人员</div>',()=>{const confirm=document.querySelector('#confirm-assignment');if(!confirm)return;confirm.onclick=async()=>{const assignee_user_id=document.querySelector('#telesales-assignee').value;confirm.disabled=true;try{await api(`/v1.2/return-verifications/tasks/${encodeURIComponent(id)}/assign`,{method:'POST',body:JSON.stringify({assignee_user_id})});toast('任务已分配');closeModal();returns()}catch(error){confirm.disabled=false;toast(error.message,true)}}})}catch(e){toast(e.message,true)}}
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
