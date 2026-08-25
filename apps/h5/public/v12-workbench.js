const API='/api/v1',app=document.querySelector('#app'),toastBox=document.querySelector('#toast'),sheet=document.querySelector('#sheet-root');
const S={me:null,view:'home',id:'',page:1};
const LABEL={DRAFT:'待完善',PENDING:'审核中',PENDING_REVIEW:'平台审核中',READY_DISPATCH:'已进入派发',DUPLICATE:'重复信息复核中',PENDING_CLAIM:'待领取',CLAIMED:'已领取',FOLLOWING:'跟进中',RETURN_PENDING:'退回处理中',RETURNED:'已退回',RELEASED:'已释放',EXPIRED:'已过期',CLOSED:'已关闭',COMPLETED:'已完成',UNCONTACTED:'未联系',CONTACTED:'已联系',INTERESTED:'有意向',NOT_INTERESTED:'无意向',DEAL:'已成交',INVALID:'需要修改',SUBMITTED:'已提交',VERIFYING:'核验中',REVIEWING:'待终审',NEED_MORE_EVIDENCE:'待补证',APPROVED:'审核通过',REJECTED:'需要修改',CLEAR:'未发现重复',HARD_DUPLICATE:'近期已有相同客户',REWARD_DUPLICATE:'已有相同客户记录',HISTORICAL_SUSPECT:'历史记录待确认',OVERRIDDEN:'已人工确认',OBSERVING:'确认中',FROZEN:'暂缓结算',SETTLED:'已结算',CANCELLED:'已取消',REVERSED:'已调整',WAITING_CLAIM:'等待领取',READ:'已读',UNREAD:'未读',EMPTY_NUMBER:'空号或停机',OUT_OF_SERVICE_REGION:'超出服务区域',DUPLICATE_TO_RECEIVER:'接收方重复客户',NON_HOUSING_CONSULTATION:'非建房装修咨询',ASSIGNED:'待处理',IN_PROGRESS:'核验中',SUPPORT_RETURN:'支持退回',DOES_NOT_SUPPORT_RETURN:'不支持退回',INCONCLUSIVE:'信息不足'};
const ROLE_HOME_CONTRACT={FRANCHISE_OWNER:'加盟商工作台',FRANCHISE_EMPLOYEE:'加盟商工作台'};
const ROLE_HOME_PRIORITY=['FRANCHISE_OWNER','FRANCHISE_EMPLOYEE'];
const FRANCHISE_HOME_CONTRACT={tabs:['home','leads','points','profile'],labels:['首页','客资','积分','我的']};
const VIEWS={home:['首页','home'],leads:['客资','list'],points:['积分','coins'],notifications:['消息','bell'],profile:['我的','user'],assignments:['接收客资','hand-claim'],returns:['退回','rotate-ccw'],rewards:['奖励','award']};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>v?new Date(v).toLocaleString('zh-CN'):'--';
const num=v=>Number(v||0).toLocaleString('zh-CN');
const icon=name=>window.ZSIconSystem?.svg(name)||'';
const TECHNICAL_CODE=/^(?:[A-Z][A-Z0-9_]{2,}|[a-z][a-z0-9]*|[a-z0-9]+(?:[_-][a-z0-9]+)+)$/;
const readableLabel=(value,fallback='待确认')=>{const text=String(value??'').trim();if(!text)return fallback;return LABEL[text]||(TECHNICAL_CODE.test(text)?fallback:text)};
const packageName=packageItem=>{const raw=String(packageItem?.name||'').trim();const fallback=readableLabel(packageItem?.level_code,'充值档位');if(!raw)return fallback;const levelNames={V1:'普通加盟商',V2:'重点加盟商',V3:'核心加盟商'};return raw.replace(/^(V1|V2|V3)\b/i,code=>levelNames[code.toUpperCase()]||fallback)};
const REWARD_REASON={REWARD_DUPLICATE:'该客户已有奖励记录',ZERO_REWARD_POINTS:'本次未产生奖励积分',FRAUD:'核对后不符合奖励条件',SYSTEM_ERROR:'系统核对后调整',ADMIN_ERROR:'平台复核后调整'};
const rewardReason=value=>{const text=String(value||'').trim();if(!text)return'';const [code,...detail]=text.split(':');const reason=REWARD_REASON[code.trim()]||readableLabel(code.trim(),'');const note=detail.join(':').trim();return [reason,note].filter(Boolean).join('：')};
const returnDecisionSummary=x=>{const reason=String(x?.final_decision_reason||'').trim();if(reason)return reason;if(x?.status==='APPROVED')return Number(x.refund_points||0)>0?`审核已通过，已返还 ${num(x.refund_points)} 积分。`:'审核已通过，积分已按规则处理。';if(x?.status==='REJECTED')return'审核未通过，请继续按原客资流程跟进。';if(x?.status==='NEED_MORE_EVIDENCE')return'请按平台说明补充沟通截图和电话录音。';return'等待平台终审';};
const recordCode=(value,prefix='记录')=>{const text=String(value??'').replace(/-/g,'');return text?`${prefix}-${text.slice(-8).toUpperCase()}`:'--'};
const badge=v=>`<span class="wb-status ${['APPROVED','CLAIMED','SETTLED','COMPLETED','READ'].includes(v)?'ok':['REJECTED','CANCELLED','REVERSED'].includes(v)?'bad':'warn'}">${esc(readableLabel(v))}</span>`;
const can=p=>(S.me?.permissions||[]).some(x=>x==='*'||x===p);
const isFranchiseOwner=()=>Boolean((S.me?.roles||[]).includes('FRANCHISE_OWNER'));
function safeDeepLink(raw){const value=String(raw||'').trim();if(!value)return '';try{const url=new URL(value,location.origin);if(url.origin!==location.origin||(!url.pathname.startsWith('/h5/')&&!url.pathname.startsWith('/admin/')))return '';return `${url.pathname}${url.search}${url.hash}`}catch{return ''}}
const WORKBENCH_REPORT_PERMISSIONS=['assignment.own.read','supplier.lead.manage','supplier.reward.own.read','points.own.read'];
const canAny=permissions=>permissions.some(can);
const canOwnReport=()=>canAny(WORKBENCH_REPORT_PERMISSIONS);
const VIEW_PERMISSION={profile:'company.profile.manage',leads:'supplier.lead.manage',points:'points.own.read',assignments:'assignment.own.read',returns:'return.own.manage',rewards:'supplier.reward.own.read',notifications:'notification.own.read'};
const canView=view=>view==='home'?canOwnReport():view==='leads'?(can('supplier.lead.manage')||can('assignment.own.read')):Boolean(VIEW_PERMISSION[view]&&can(VIEW_PERMISSION[view]));
function defaultWorkbenchView(){
  if(canView('home'))return 'home';
  if(canView('leads'))return 'leads';
  if(canView('points'))return 'points';
  if(canView('notifications'))return 'notifications';
  if(canView('profile'))return 'profile';
  if(canView('returns'))return 'returns';
  return 'home';
}
async function api(path,opt={}){const h={...(opt.headers||{})};if(opt.body&&!(opt.body instanceof FormData))h['Content-Type']='application/json';const r=await fetch(API+path,{...opt,headers:h,credentials:'include'});let j={};try{j=await r.json()}catch{}if(!r.ok||j.code!=='OK'){const error=new Error(j.message||'请求失败');error.code=j.code;throw error}return j.data}
function toast(msg,err=false){toastBox.textContent=msg;toastBox.className=`workbench-toast show ${err?'error':''}`;clearTimeout(toast.t);toast.t=setTimeout(()=>toastBox.className='workbench-toast',2200)}
function closeSheet(){sheet.innerHTML=''}
function openSheet(title,html,bind){zsSetSafeHtml(sheet, `<div class="wb-overlay"><section class="wb-sheet"><div class="wb-sheet-head"><h2>${esc(title)}</h2><button class="wb-btn" id="sheet-close">关闭</button></div>${html}</section></div>`);document.querySelector('#sheet-close').onclick=closeSheet;bind?.()}
function nav(){return FRANCHISE_HOME_CONTRACT.tabs.map(k=>{const [n,i]=VIEWS[k];const locked=!canView(k);const active=S.view===k||(S.view==='notifications'&&k==='profile');return `<button class="wb-nav ${active?'active':''} ${locked?'locked':''}" data-nav="${k}" aria-disabled="${locked?'true':'false'}"><span>${icon(i)}</span><span>${n}</span></button>`}).join('')}
function shell(body){zsSetSafeHtml(app, `<div class="workbench-shell"><header class="wb-header"><div class="wb-brand"><img class="wb-mark" src="./logo.png" alt="合家美宅"><div><strong>合家美宅</strong><small>${esc(S.me?.display_name||'')} · 加盟商</small></div></div><div class="wb-header-actions"><button class="wb-icon-btn" id="wb-refresh">${icon('rotate-ccw')}<span>刷新</span></button><button class="wb-icon-btn" id="wb-logout">${icon('log-out')}<span>退出</span></button></div></header><main class="wb-main">${body}</main><nav class="wb-bottom">${nav()}</nav></div>`);document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>go(b.dataset.nav));document.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>go(b.dataset.go,b.dataset.id||''));document.querySelectorAll('[data-scroll]').forEach(b=>b.onclick=()=>document.getElementById(b.dataset.scroll)?.scrollIntoView({behavior:'smooth',block:'start'}));document.querySelector('#wb-refresh').onclick=render;document.querySelector('#wb-logout').onclick=async()=>{await api('/auth/logout',{method:'POST'}).catch(()=>{});location.replace('/h5/')}}
function go(view,id=''){if(!canView(view)){toast('当前账号暂未开通该栏目');view=defaultWorkbenchView();id=''}S.view=view;S.id=id;S.page=1;const u=new URL(location.href);u.searchParams.set('view',view);id?u.searchParams.set('id',id):u.searchParams.delete('id');history.replaceState(null,'',u);render()}
function item(title,status,body,actions=''){return `<article class="wb-item"><div class="wb-item-top"><div><h3>${esc(title)}</h3>${body}</div>${badge(status)}</div>${actions?`<div class="wb-actions">${actions}</div>`:''}</article>`}
function metricCard(labelText,value,{view='',id='',scroll='',main=false}={}){const destination=view?`data-go="${esc(view)}"${id?` data-id="${esc(id)}"`:''}`:scroll?`data-scroll="${esc(scroll)}"`:'';return `<button type="button" class="wb-kpi${main?' main':''}" ${destination} aria-label="${esc(labelText)}：${esc(value??0)}，查看详情"><b>${esc(value??0)}</b><span>${esc(labelText)}</span><i aria-hidden="true">${icon('chevron-right')}</i></button>`}
async function render(){shell('<div class="wb-loading">加载中…</div>');try{if(S.view==='home')await home();else if(S.view==='profile')await profile();else if(S.view==='leads')await leadCenter();else if(S.view==='points')await points();else if(S.view==='assignments')await assignments();else if(S.view==='returns')await returns();else if(S.view==='rewards')await rewards();else await notifications()}catch(e){shell(`<div class="wb-error">${esc(e.message)}</div>`);toast(e.message,true)}}
async function home(){
  const companyId=S.me?.company_id;
  const accountRequest=can('points.own.read')&&companyId?api(`/points/accounts/${encodeURIComponent(companyId)}`):Promise.resolve(null);
  const [d,account]=await Promise.all([api('/v1.2/reports/own'),accountRequest]);
  const received=d.received_assignments?.by_status||{};
  const returnsByStatus=d.returns?.by_status||{};
  const waitingClaim=Number(received.PENDING_CLAIM||0);
  const following=Number(received.CLAIMED||0)+Number(received.FOLLOWING||0);
  const returnProcessing=Number(returnsByStatus.VERIFYING||0)+Number(returnsByStatus.REVIEWING||0)+Number(returnsByStatus.NEED_MORE_EVIDENCE||0);
  const supplierLeadTotal=Number(d.supplier_leads?.total||0);
  const receivedTotal=Number(d.received_assignments?.total||0);
  const rewardByStatus=d.supplier_rewards?.by_status||{};
  const rewardAttention=Number(rewardByStatus.OBSERVING||0)+Number(rewardByStatus.FROZEN||0);
  const rewardTotal=Number(d.supplier_rewards?.total||0);
  const heroMetrics=[];
  const addHeroMetric=(labelText,value,destination)=>heroMetrics.push(metricCard(labelText,value,{...destination,main:heroMetrics.length===0}));
  if(canView('points'))addHeroMetric('可用于领取',num(account?.available_for_dispatch??account?.balance),{view:'points'});
  if(canView('assignments')){
    addHeroMetric('待领取',waitingClaim,{view:'assignments'});
    addHeroMetric('待跟进',following,{view:'assignments'});
  }
  if(canView('returns'))addHeroMetric('退回处理中',returnProcessing,{view:'returns'});
  if(can('supplier.lead.manage'))addHeroMetric('已供客资',supplierLeadTotal,{view:'leads',id:'supply'});
  if(canView('rewards'))addHeroMetric('待关注奖励',rewardAttention,{view:'rewards'});
  if(heroMetrics.length>4)heroMetrics.length=4;
  const primary=waitingClaim&&canView('assignments')?['assignments','去领取客资']:following&&canView('assignments')?['assignments','继续跟进']:canView('leads')?['leads','查看客资']:canView('points')?['points','查看积分']:canView('rewards')?['rewards','查看奖励']:canView('profile')?['profile','完善资料']:[defaultWorkbenchView(),'刷新工作台'];
  shell(`<section class="wb-hero wb-home-hero"><h1>合家美宅加盟商工作台</h1><p>只展示当前账号可处理的数据，点击数字直达对应列表。</p><div class="wb-kpis">${heroMetrics.join('')}</div><button class="wb-btn primary wb-primary-cta" data-go="${primary[0]}">${icon(primary[0]==='assignments'?'inbox':'chevron-right')}<span>${primary[1]}</span></button></section><div class="wb-grid">${can('assignment.own.read')?`<button type="button" class="wb-card wb-action-card" data-go="leads"><div class="wb-action-icon">${icon('hand-claim')}</div><b>接收客资</b><strong class="wb-action-value">${receivedTotal} 条</strong><span class="wb-muted">领取、跟进并查看退回状态</span></button>`:''}${can('supplier.lead.manage')?`<button type="button" class="wb-card wb-action-card" data-go="leads" data-id="supply"><div class="wb-action-icon">${icon('plus')}</div><b>上传客资</b><strong class="wb-action-value">${supplierLeadTotal} 条</strong><span class="wb-muted">提交客户资料并查看平台审核进度</span></button>`:''}${can('points.own.read')?`<button type="button" class="wb-card wb-action-card" data-go="points"><div class="wb-action-icon">${icon('coins')}</div><b>积分</b><strong class="wb-action-value">${num(account?.balance)} 分</strong><span class="wb-muted">查看余额、占用和最近流水</span></button>`:''}${can('company.profile.manage')?`<button type="button" class="wb-card wb-action-card" data-go="profile"><div class="wb-action-icon">${icon('user')}</div><b>公司资料与接单能力</b><strong class="wb-action-value">去维护</strong><span class="wb-muted">维护服务区域和供接客资能力</span></button>`:''}${can('return.own.manage')?`<button type="button" class="wb-card wb-action-card" data-go="returns"><div class="wb-action-icon">${icon('rotate-ccw')}</div><b>退回申诉</b><strong class="wb-action-value">${returnProcessing} 条处理中</strong><span class="wb-muted">提交证据并查看审核进度</span></button>`:''}${can('supplier.reward.own.read')?`<button type="button" class="wb-card wb-action-card" data-go="rewards"><div class="wb-action-icon">${icon('award')}</div><b>供客奖励</b><strong class="wb-action-value">${rewardTotal} 笔</strong><span class="wb-muted">查看确认中和已到账奖励</span></button>`:''}</div>`);
}
const CAPABILITY_META={
  LEAD_SUPPLIER:{title:'客资供应能力',description:'审核通过后可上传客资并查看初审状态。'},
  LEAD_RECEIVER:{title:'客资接收能力',description:'审核通过且服务区域生效后可进入派单候选。'},
};
const REMOVAL_REQUEST_PREFIX='[REMOVE_REQUEST]';
const cleanReviewNote=note=>String(note||'').replace(/^\[REMOVE_REQUEST\]\s*/,'');
const removalPending=item=>String(item.review_note||'').startsWith(REMOVAL_REQUEST_PREFIX);
function capabilityCard(capabilities,code){
  const meta=CAPABILITY_META[code];
  const capability=capabilities.find(item=>item.capability_code===code);
  const approved=Boolean(capability?.active&&capability?.review_status==='APPROVED');
  const state=approved?'已开通':capability?.review_status==='PENDING'?'审核中':capability?.review_status==='REJECTED'?'已驳回':'未申请';
  const action=approved
    ?'<span class="wb-muted">能力已开通；如需停用，请联系平台管理员。</span>'
    :capability?.review_status==='PENDING'
      ?'<span class="wb-muted">申请正在审核中，无需重复提交。</span>'
      :'<button class="wb-btn primary" data-capability-request="'+esc(code)+'">'+(capability?'重新申请':'提交申请')+'</button>';
  const note=capability?.review_note?'<div class="wb-notice">平台说明：'+esc(cleanReviewNote(capability.review_note))+'</div>':'';
  return '<article class="wb-item"><div class="wb-item-top"><div><h3>'+esc(meta.title)+'</h3><p>'+esc(meta.description)+'</p></div>'+(capability?badge(capability.review_status):'<span class="wb-status warn">未申请</span>')+'</div><div class="wb-detail-grid">'+[
    ['审核状态',state],
    ['当前可用',approved?'是':'否'],
    ['审核时间',fmt(capability?.reviewed_at)],
  ].map(([name,value])=>'<div class="wb-detail"><small>'+esc(name)+'</small><b>'+esc(value||'--')+'</b></div>').join('')+'</div>'+note+'<div class="wb-actions">'+action+'</div></article>';
}
async function profile(){
  if(!can('company.profile.manage')){shell('<div class="wb-error">无权访问加盟商设置</div>');return}
  const [report,capabilities,areas,cities]=await Promise.all([
    api('/v1.2/reports/own'),
    api('/v1.2/company/capabilities'),
    api('/v1.2/company/service-areas'),
    api('/master-data/regions?level=CITY'),
  ]);
  const cityCodes=[...new Set(areas.filter(item=>item.region_level==='CITY').map(item=>item.region_code))];
  const districtGroups=await Promise.all(cityCodes.map(code=>api('/master-data/regions?parent_code='+encodeURIComponent(code)+'&level=DISTRICT')));
  const regions=[...cities,...districtGroups.flat()];
  const regionNames=Object.fromEntries(regions.map(region=>[region.code,region.name]));
  const approvedCapabilities=capabilities.filter(item=>item.active&&item.review_status==='APPROVED').length;
  const pendingCapabilities=capabilities.filter(item=>item.review_status==='PENDING').length;
  const approvedAreas=areas.filter(item=>item.active&&(item.review_status==='APPROVED'||removalPending(item))).length;
  const primaryCities=new Set(areas.filter(item=>item.is_primary_city&&item.active).map(item=>item.region_code));
  const unreadNotifications=Number(report?.unread_notifications||0);
  const areaCards=areas.length?areas.map(item=>{
    const state=removalPending(item)&&item.active?'待审核移除（当前仍生效）':item.active?'已生效':'未生效';
    const note=item.review_note?'<p>平台说明：'+esc(cleanReviewNote(item.review_note))+'</p>':'';
    return '<article class="wb-item"><div class="wb-item-top"><div><h3>'+esc(item.is_primary_city?'主要城市':'服务区域')+' · '+esc(regionNames[item.region_code]||'待补充地区名称')+'</h3><p>'+esc(state)+'</p>'+note+'<p>审核时间 '+fmt(item.reviewed_at)+'</p></div>'+badge(item.review_status)+'</div></article>';
  }).join(''):'<div class="wb-empty service-area-empty">暂无服务区域申请</div>';
  const messageCard=canView('notifications')?`<section class="wb-card wb-profile-message"><div class="wb-card-head"><div><h2>消息中心</h2><p>平台通知、审核提醒和进度更新都在这里。</p></div><button class="wb-btn primary" data-go="notifications">查看 ${unreadNotifications} 条未读消息</button></div></section>`:'';
  shell('<section class="wb-hero"><h1>公司资料与接单能力</h1><p>供客能力、接收能力和服务区域分别审核。点击数字可直达对应资料。</p><div class="wb-kpis">'+metricCard('已开通能力',approvedCapabilities,{scroll:'company-capabilities'})+metricCard('待审能力',pendingCapabilities,{scroll:'company-capabilities'})+metricCard('当前有效区域',approvedAreas,{scroll:'service-areas'})+metricCard('主要城市',primaryCities.size,{scroll:'service-areas'})+'</div></section>'+messageCard+'<div class="wb-profile-grid"><section class="wb-card" id="company-capabilities"><div class="wb-card-head"><div><h2>公司客资能力</h2><p>供客与接收能力独立申请、独立启停。</p></div></div><div class="wb-list">'+Object.keys(CAPABILITY_META).map(code=>capabilityCard(capabilities,code)).join('')+'</div></section><section class="wb-card" id="service-areas"><div class="wb-card-head"><div><h2>服务区域</h2><p>主要城市必须包含在申请中，区县与城市一起审核。</p></div><button class="wb-btn primary" id="service-area-edit">申请/更新</button></div><div class="wb-list" id="service-area-list">'+areaCards+'</div></section></div>');
  document.querySelectorAll('[data-capability-request]').forEach(button=>button.onclick=()=>requestCapability(button));
  document.querySelectorAll('[data-go]').forEach(button=>button.onclick=()=>go(button.dataset.go));
  document.querySelector('#service-area-edit').onclick=()=>editServiceAreas(areas);
}
async function requestCapability(button){
  if(button.dataset.busy==='1')return;
  const capabilityCode=button.dataset.capabilityRequest;
  button.dataset.busy='1';button.disabled=true;
  try{
    await api('/v1.2/company/capabilities',{method:'POST',body:JSON.stringify({capability_code:capabilityCode})});
    toast(CAPABILITY_META[capabilityCode].title+'申请已提交');
    await profile();
  }catch(error){
    delete button.dataset.busy;button.disabled=false;toast(error.message,true);
  }
}
async function editServiceAreas(existingAreas){
  const cities=await api('/master-data/regions?level=CITY');
  const effectiveAreas=existingAreas.filter(item=>item.active);
  const desiredAreas=existingAreas.filter(item=>!removalPending(item));
  const currentPrimary=desiredAreas.find(item=>item.is_primary_city&&item.region_level==='CITY')?.region_code||effectiveAreas.find(item=>item.is_primary_city&&item.region_level==='CITY')?.region_code||desiredAreas.find(item=>item.region_level==='CITY')?.region_code||effectiveAreas.find(item=>item.region_level==='CITY')?.region_code||cities[0]?.code||'';
  let selectedCity=currentPrimary;
  let districts=[];
  let selectedDistrictCodes=new Set(desiredAreas.filter(item=>item.region_level==='DISTRICT').map(item=>item.region_code));
  const renderDistrictChoices=()=>{
    const root=document.querySelector('#service-area-districts');
    if(!root)return;
    const html=districts.length
      ?districts.map(item=>'<label class="wb-choice"><input type="checkbox" value="'+esc(item.code)+'" '+(selectedDistrictCodes.has(item.code)?'checked':'')+'><span>'+esc(item.name)+'</span></label>').join('')
      :'<div class="wb-empty service-area-empty">该城市暂无可选区县</div>';
    zsSetSafeHtml(root,html);
  };
  const loadDistricts=async cityCode=>{
    districts=cityCode?await api('/master-data/regions?parent_code='+encodeURIComponent(cityCode)+'&level=DISTRICT'):[];
    renderDistrictChoices();
  };
  const cityOptions=cities.map(item=>'<option value="'+esc(item.code)+'" '+(item.code===selectedCity?'selected':'')+'>'+esc(item.name)+'</option>').join('');
  openSheet('申请/更新服务区域','<form class="wb-form" id="service-area-form"><div class="wb-notice">待移除区域在审核前仍生效；重新勾选并提交可撤销移除申请。</div><div class="wb-field"><label>主要城市</label><select class="wb-select" name="city" id="service-area-city">'+cityOptions+'</select><small class="wb-muted">主要城市必须包含在申请区域中。</small></div><div class="wb-field"><label>服务区县</label><div class="wb-list" id="service-area-districts"><div class="wb-empty service-area-empty">正在加载区县…</div></div><small class="wb-muted">可以只提交城市，也可以叠加多个区县。</small></div><button class="wb-btn primary" id="service-area-submit">提交审核</button></form>',()=>{
    const form=document.querySelector('#service-area-form');
    const citySelect=document.querySelector('#service-area-city');
    const submitButton=document.querySelector('#service-area-submit');
    let submitting=false;
    const syncSelection=()=>{selectedDistrictCodes=new Set([...document.querySelectorAll('#service-area-districts input:checked')].map(item=>item.value))};
    citySelect.onchange=async event=>{selectedCity=event.target.value;selectedDistrictCodes=new Set();await loadDistricts(selectedCity)};
    document.querySelector('#service-area-districts').addEventListener('change',syncSelection);
    form.onsubmit=async event=>{
      event.preventDefault();
      if(submitting)return;
      syncSelection();
      if(!selectedCity){toast('请选择主要城市',true);return}
      submitting=true;submitButton.disabled=true;
      const regionCodes=[selectedCity,...selectedDistrictCodes];
      try{
        await api('/v1.2/company/service-areas',{method:'PUT',body:JSON.stringify({primary_city_code:selectedCity,region_codes:[...new Set(regionCodes)]})});
        closeSheet();toast('服务区域申请已提交');await profile();
      }catch(error){
        submitting=false;submitButton.disabled=false;toast(error.message,true);
      }
    };
    loadDistricts(selectedCity);
  });
}
async function leadCenter(){const tabs=[];if(can('assignment.own.read'))tabs.push(`<button class="wb-btn ${S.id==='supply'?'':'primary'}" data-lead-tab="receive">接收客资</button>`);if(can('supplier.lead.manage'))tabs.push(`<button class="wb-btn ${S.id==='supply'?'primary':''}" data-lead-tab="supply">供应客资</button>`);const useSupply=S.id==='supply'||!can('assignment.own.read');if(useSupply)await leads(tabs.join(''));else await assignments(tabs.join(''))}
function ledgerLabel(type){return {RECHARGE:'充值入账',CLAIM:'领取扣分',RETURN:'退回返分',REWARD:'奖励到账',ADJUST:'人工调整',REVERSAL:'冲正调整'}[type]||readableLabel(type,'积分变动')}
function monthDelta(rows){const now=new Date(),start=new Date(now.getFullYear(),now.getMonth(),1);return rows.filter(x=>new Date(x.created_at)>=start).reduce((sum,x)=>sum+Number(x.delta||0),0)}
async function points(){
  const companyId=S.me?.company_id;
  if(!companyId){shell('<div class="wb-error">无法读取当前公司信息</div>');return}
  const [account,ledgers,packages]=await Promise.all([api(`/points/accounts/${encodeURIComponent(companyId)}`),api(`/points/ledgers?company_id=${encodeURIComponent(companyId)}&page=1&page_size=50`),api('/points/packages')]);
  const rows=ledgers.items||[];
  const delta=monthDelta(rows);
  const assignmentMetricTarget=canView('assignments')?{view:'assignments'}:{scroll:'points-ledger'};
  const ledgerList=rows.slice(0,8).map(x=>`<article class="wb-item wb-ledger"><div class="wb-item-top"><div><h3>${esc(ledgerLabel(x.type))}</h3><p>${fmt(x.created_at)} · 余额 ${num(x.balance_after)} 分</p></div><b class="${Number(x.delta||0)>=0?'plus':'minus'}">${Number(x.delta||0)>=0?'+':''}${num(x.delta)} 分</b></div></article>`).join('');
  const packageList=(packages||[]).slice(0,3).map(p=>`<article class="wb-item"><div class="wb-item-top"><div><h3>${esc(packageName(p))}</h3><p>线下实收 ¥${num(Number(p.cash_amount_cents||0)/100)} · 到账 ${num(Number(p.base_points||0)+Number(p.bonus_points||0))} 分</p></div></div></article>`).join('');
  shell(`<section class="wb-hero wb-points-hero"><h1>积分</h1><p>余额、占用和流水分开显示，点击数字可直达对应明细。</p><div class="wb-kpis">${metricCard('当前余额',num(account.balance),{scroll:'points-ledger',main:true})}${metricCard('本月变化',`${delta>=0?'+':''}${num(delta)}`,{scroll:'points-ledger'})}${metricCard('可用于领取',num(account.available_for_dispatch),assignmentMetricTarget)}${metricCard('待领取占用',num(account.pending_claim_points),assignmentMetricTarget)}</div></section><div class="wb-profile-grid"><section class="wb-card" id="points-ledger"><div class="wb-card-head"><div><h2>积分流水</h2></div></div><div class="wb-list">${ledgerList||'<div class="wb-empty">暂无积分流水</div>'}</div></section><section class="wb-card" id="points-packages"><div class="wb-card-head"><div><h2>线下充值</h2><p>请联系平台财务确认付款方式。</p></div></div><div class="wb-list wb-package-list">${packageList||'<div class="wb-empty">暂无可参考充值档位</div>'}</div>${can('supplier.reward.own.read')?'<div class="wb-actions"><button class="wb-btn" data-go="rewards">查看奖励积分</button></div>':''}</section></div>`);
}
async function leads(tabBar=''){const d=await api(`/v1.2/supplier/leads?page=${S.page}&page_size=20`);const list=(d.items||[]).map(x=>item(x.customer_name==='未填写'?'未填写姓名':x.customer_name||'未填写姓名',x.status,`<p>${esc(x.phone_masked||'手机号待补充')} · ${esc(x.city||'地区待补充')} ${esc(x.district||'')}</p><p>${esc(x.need_summary||'需求待补充')}</p>`,`<button class="wb-btn" data-lead="${x.id}">查看进度</button>`)).join('');const empty='<div class="wb-empty">还没有供应客资<br><a class="wb-btn primary" href="./supplier.html">上传第一条客资</a></div>';shell(`<div class="wb-card-head"><div><h2>客资 · 供应客资</h2><p>查看平台审核、重复复核和派发进度。</p></div><a class="wb-btn primary" href="./supplier.html">上传新客资</a></div>${tabBar?`<div class="wb-actions">${tabBar}</div>`:''}<div class="wb-list">${list||empty}</div>`);document.querySelectorAll('[data-lead-tab]').forEach(b=>b.onclick=()=>{S.id=b.dataset.leadTab==='supply'?'supply':'';leadCenter()});document.querySelectorAll('[data-lead]').forEach(b=>b.onclick=()=>leadDetail(b.dataset.lead));if(S.id&&S.id!=='supply'){const id=S.id;S.id='';leadDetail(id)}}
async function leadDetail(id){const x=await api(`/v1.2/supplier/leads/${id}`);const fields=[['客户',x.customer_name==='未填写'?'未填写':x.customer_name],['手机号',x.phone_masked],['服务地区',`${x.city||''} ${x.district||''}`.trim()],['当前进度',readableLabel(x.status)],['资料审核',readableLabel(x.review_status)],['重复情况',x.duplicate_status?readableLabel(x.duplicate_status,'平台复核中'):null],['提交时间',fmt(x.submitted_at)],['最后更新',fmt(x.updated_at)]].filter(([,value])=>value);openSheet('客资进度',`<div class="wb-detail-grid">${fields.map(([a,b])=>`<div class="wb-detail"><small>${a}</small><b>${esc(b)}</b></div>`).join('')}</div><div class="wb-card"><h3>客户需求</h3><p class="wb-muted">${esc(x.need_summary||'尚未填写')}</p></div>${x.review_note?`<div class="wb-notice">平台说明：${esc(x.review_note)}</div>`:''}${x.status==='INVALID'?'<a class="wb-btn primary" href="./supplier.html">前往修改</a>':''}`)}
async function assignments(tabBar=''){
  const companyId=S.me?.company_id;
  const canManageInternal=isFranchiseOwner()&&can('assignment.own.read')&&Boolean(companyId);
  const [d,directory]=await Promise.all([
    api(`/v1.2/assignments?page=${S.page}&page_size=20`),
    canManageInternal?api(`/companies/${encodeURIComponent(companyId)}/account-directory`):Promise.resolve([]),
  ]);
  const employeeName=userId=>(directory||[]).find(user=>user.id===userId)?.display_name||'';
  const canCollaborate=status=>['CLAIMED','FOLLOWING','RETURN_PENDING'].includes(status);
  const list=(d.items||[]).map(x=>{
    const currentAssignee=employeeName(x.internal_assignee_user_id);
    const collaboration=canManageInternal&&canCollaborate(x.status)?`<p>内部处理：${esc(currentAssignee||'负责人自己跟进')}</p>`:'';
    const manage=canManageInternal&&canCollaborate(x.status)?`<button class="wb-btn" data-internal-assignment="${x.id}">分配员工</button>`:'';
    return item(x.customer_name||x.lead?.customer_name||'客户',x.status,`<p>${esc(x.phone||x.phone_masked||'领取后查看')} · ${esc(x.city||x.lead?.city||'')}</p><p>客资积分 ${x.points_price||0} · 领取截止 ${fmt(x.claim_deadline_at)}</p>${collaboration}`,`<button class="wb-btn" data-assignment="${x.id}">详情</button>${x.status==='PENDING_CLAIM'&&can('assignment.own.claim')?`<button class="wb-btn primary" data-claim="${x.id}">领取</button>`:''}${manage}`);
  }).join('');
  const collaborationNotice=canManageInternal?'<div class="wb-notice">负责人可在公司内部直接分配，无需运营审批；员工仅可看到分配给自己的客资。</div>':'';
  shell(`<div class="wb-card-head"><div><h2>客资 · 接收客资</h2><p>领取前隐藏明文电话，领取成功后可查看完整联系方式。</p></div></div>${tabBar?`<div class="wb-actions">${tabBar}</div>`:''}${collaborationNotice}<div class="wb-list">${list||'<div class="wb-empty">暂无派发单</div>'}</div>`);
  document.querySelectorAll('[data-lead-tab]').forEach(b=>b.onclick=()=>{S.id=b.dataset.leadTab==='supply'?'supply':'';leadCenter()});
  document.querySelectorAll('[data-assignment]').forEach(b=>b.onclick=()=>assignmentDetail(b.dataset.assignment));
  document.querySelectorAll('[data-claim]').forEach(b=>b.onclick=()=>claim(b.dataset.claim));
  document.querySelectorAll('[data-internal-assignment]').forEach(b=>b.onclick=()=>manageInternalAssignment(b.dataset.internalAssignment));
  if(S.id&&S.id!=='supply'){const id=S.id;S.id='';assignmentDetail(id)}
}
async function assignmentDetail(id){const [x,followups]=await Promise.all([api(`/v1.2/assignments/${id}`),api(`/followups/assignments/${id}`)]);const history=(followups||[]).map(row=>`<article class="wb-item"><div class="wb-item-top"><div><h3>${esc(readableLabel(row.status,'状态已更新'))}</h3><p>${esc(row.note||'无备注')}</p><p>记录时间 ${fmt(row.created_at)}${row.next_followup_at?` · 下次跟进 ${fmt(row.next_followup_at)}`:''}</p></div></div></article>`).join('');const currentFollow=x.current_follow_status||followups?.[0]?.status;const canFollow=['CLAIMED','FOLLOWING'].includes(x.status)&&can('followup.own.manage');openSheet('派发单详情',`<div class="wb-detail-grid">${[['派发编号',recordCode(x.id,'PF')],['客户',x.customer_name],['电话',x.phone||x.phone_masked||'领取后查看'],['派发状态',readableLabel(x.status)],['客资状态',readableLabel(x.lead_status)],['当前跟进',currentFollow?readableLabel(currentFollow):'暂无'],['客资积分',x.points_price],['申诉截止',fmt(x.appeal_deadline_at)]].map(([a,b])=>`<div class="wb-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><div class="wb-actions">${x.status==='PENDING_CLAIM'&&can('assignment.own.claim')?`<button class="wb-btn primary" id="sheet-claim">领取客资</button>`:''}${canFollow?`<button class="wb-btn primary" id="sheet-followup">新增跟进</button>`:''}${['CLAIMED','FOLLOWING'].includes(x.status)&&can('return.own.manage')?`<button class="wb-btn danger" id="sheet-return">发起退回</button>`:''}</div><div class="wb-card"><h3>跟进历史</h3><div class="wb-list">${history||'<div class="wb-empty">暂无跟进记录</div>'}</div></div>`,()=>{document.querySelector('#sheet-claim')?.addEventListener('click',()=>claim(id));document.querySelector('#sheet-followup')?.addEventListener('click',()=>followupDraft(id));document.querySelector('#sheet-return')?.addEventListener('click',()=>returnDraft(id))})}
async function claim(id){try{await api(`/v1.2/assignments/${id}/claim`,{method:'POST'});toast('领取成功');closeSheet();render()}catch(e){toast(e.message,true)}}
async function manageInternalAssignment(assignmentId){
  const companyId=S.me?.company_id;
  if(!isFranchiseOwner()||!companyId){toast('仅加盟商负责人可分配员工',true);return}
  try{
    const [assignment,directory]=await Promise.all([
      api(`/v1.2/assignments/${encodeURIComponent(assignmentId)}`),
      api(`/companies/${encodeURIComponent(companyId)}/account-directory`),
    ]);
    const employees=(directory||[]).filter(user=>user.role_code==='FRANCHISE_EMPLOYEE'&&user.status==='ACTIVE');
    const currentEmployee=employees.find(user=>user.id===assignment.internal_assignee_user_id)?.id||'';
    const options=[`<option value="">负责人自己跟进</option>`,...employees.map(user=>`<option value="${esc(user.id)}" ${user.id===currentEmployee?'selected':''}>${esc(user.display_name||'未命名员工')}</option>`)].join('');
    openSheet('分配员工',`<div class="wb-notice">公司内部直接分配，无需运营审批。选择“负责人自己跟进”可收回该客资，系统会保留交接记录。</div><form class="wb-form" id="internal-assignment-form"><div class="wb-field"><label>处理人员</label><select class="wb-select" name="employee_user_id">${options}</select></div><div class="wb-field"><label>分配或回收原因</label><textarea class="wb-textarea" name="reason" required minlength="2" maxlength="500" placeholder="例如：转交负责该区域的销售跟进"></textarea></div><button class="wb-btn primary" id="internal-assignment-submit">保存分配</button></form>`,()=>{
      const form=document.querySelector('#internal-assignment-form'),submit=document.querySelector('#internal-assignment-submit');
      form.onsubmit=async event=>{
        event.preventDefault();
        const fields=new FormData(form),reason=String(fields.get('reason')||'').trim(),employeeUserId=String(fields.get('employee_user_id')||'').trim();
        if(reason.length<2){toast('请至少填写 2 个字的分配或回收原因',true);return}
        submit.disabled=true;
        try{
          await api(`/v1.2/assignments/${encodeURIComponent(assignmentId)}/internal-assignee`,{method:'POST',body:JSON.stringify({employee_user_id:employeeUserId||null,reason})});
          toast(employeeUserId?'已分配给员工':'已收回到负责人');
          closeSheet();
          render();
        }catch(error){submit.disabled=false;toast(error.message,true)}
      };
    });
  }catch(error){toast(error.message,true)}
}
function followupDraft(assignmentId){openSheet('新增跟进',`<form class="wb-form" id="followup-form"><div class="wb-field"><label>跟进状态</label><select class="wb-select" name="status"><option value="CONTACTED">已联系</option><option value="INTERESTED">有意向</option><option value="NOT_INTERESTED">无意向</option><option value="DEAL">已成交</option><option value="INVALID">无效客资</option><option value="UNCONTACTED">未联系</option></select><small class="wb-muted">无效客资必须进入正式退回申诉，不能只保存为跟进标签。</small></div><div class="wb-field"><label>跟进备注</label><textarea class="wb-textarea" name="note" maxlength="500" placeholder="填写沟通结果或后续安排"></textarea></div><div class="wb-field"><label>下次跟进时间</label><input class="wb-input" type="datetime-local" name="next_followup_at"><small class="wb-muted">选择方便再次联系客户的时间。</small></div><button class="wb-btn primary" id="followup-submit">保存跟进</button></form>`,()=>{const form=document.querySelector('#followup-form'),submitButton=document.querySelector('#followup-submit'),statusField=form.elements.status;const syncSubmitLabel=()=>{submitButton.textContent=statusField.value==='INVALID'?'下一步：发起退回':'保存跟进'};statusField.onchange=syncSubmitLabel;syncSubmitLabel();let submitting=false;form.onsubmit=async e=>{e.preventDefault();if(submitting)return;const fields=Object.fromEntries(new FormData(form));if(fields.status==='INVALID'){closeSheet();returnDraft(assignmentId,String(fields.note||'').trim());return}submitting=true;submitButton.disabled=true;const nextFollowupAt=String(fields.next_followup_at||'').trim();let nextFollowupAtIso=null;if(nextFollowupAt){const parsed=new Date(nextFollowupAt);if(Number.isNaN(parsed.getTime())){submitting=false;submitButton.disabled=false;toast('下次跟进时间格式不正确',true);return}nextFollowupAtIso=new Date(nextFollowupAt).toISOString()}try{await api(`/followups/assignments/${assignmentId}`,{method:'POST',body:JSON.stringify({status:fields.status,note:String(fields.note||'').trim()||null,next_followup_at:nextFollowupAtIso})})}catch(err){submitting=false;submitButton.disabled=false;if(err.code==='FOLLOWUP_INVALID_REQUIRES_RETURN'){closeSheet();returnDraft(assignmentId,String(fields.note||'').trim());return}toast(err.message,true);return}toast('跟进已保存');try{await assignmentDetail(assignmentId)}catch{closeSheet();toast('跟进已保存，请刷新查看',true)}}})}
function returnDraft(assignmentId,initialDescription=''){openSheet('发起退回申诉',`<form class="wb-form" id="return-form"><div class="wb-field"><label>退回原因</label><select class="wb-select" name="reason_code"><option value="EMPTY_NUMBER">空号/停机</option><option value="OUT_OF_SERVICE_REGION">超出服务区域</option><option value="DUPLICATE_TO_RECEIVER">接收方重复客户</option><option value="NON_HOUSING_CONSULTATION">非建房咨询</option></select></div><div class="wb-field"><label>事实说明</label><textarea class="wb-textarea" name="description" required minlength="5" placeholder="请说明联系次数、沟通结果和申请退回的事实依据">${esc(initialDescription)}</textarea></div><button class="wb-btn primary">下一步：上传证据</button></form>`,()=>{document.querySelector('#return-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);try{const x=await api(`/v1.2/returns/assignments/${assignmentId}/draft`,{method:'POST',body:JSON.stringify(Object.fromEntries(f))});closeSheet();evidence(x.id,x.evidence_summary||{})}catch(err){toast(err.message,true)}}})}
function evidence(returnId,summary={}){
  const uploadedTypes=new Set();
  if(Number(summary.CHAT_SCREENSHOT||0)>0)uploadedTypes.add('CHAT_SCREENSHOT');
  if(Number(summary.CALL_RECORDING||0)>0)uploadedTypes.add('CALL_RECORDING');
  openSheet('上传证据并提交',`<div class="wb-notice"><b>截图或录音任一类型满足即可。</b><br>截图用于确认沟通内容，录音用于后续电销和审核人员核实事实。</div><form class="wb-form" id="evidence-form"><div class="wb-field"><label>沟通截图</label><input class="wb-input" type="file" name="chat_screenshots" accept="image/jpeg,image/png,image/webp" multiple><small class="wb-muted">支持 JPG、PNG、WEBP，可选择多张。</small></div><div class="wb-field"><label>电话录音</label><input class="wb-input" type="file" name="call_recording" accept="audio/mpeg,audio/wav,audio/mp4,audio/aac"><small class="wb-muted">支持 MP3、WAV、M4A、AAC，最大 20MB。</small></div><button class="wb-btn" id="upload-evidence" type="submit">上传证据</button></form><p class="wb-muted" id="evidence-progress" role="status">${uploadedTypes.size>0?'已有证据，可以提交退回申请。':'请至少上传一种证据。'}</p><button class="wb-btn primary" id="submit-return" style="margin-top:12px" ${uploadedTypes.size>0?'':'disabled'}>提交退回申请</button>`,()=>{
    const form=document.querySelector('#evidence-form');
    const uploadButton=document.querySelector('#upload-evidence');
    const submitButton=document.querySelector('#submit-return');
    const progress=document.querySelector('#evidence-progress');
    const uploadFile=async(file,type)=>{const body=new FormData();body.append('file',file);body.append('evidence_type',type);await api(`/v1.2/returns/${returnId}/evidence`,{method:'POST',body})};
    form.onsubmit=async event=>{
      event.preventDefault();
      const screenshots=Array.from(form.elements.chat_screenshots.files||[]);
      const recording=form.elements.call_recording.files?.[0];
      if(uploadedTypes.size===0&&!screenshots.length&&!recording){toast('请至少上传沟通截图或电话录音',true);return}
      uploadButton.disabled=true;
      progress.textContent='正在上传证据，请不要关闭页面…';
      try{
        if(screenshots.length){for(const file of screenshots)await uploadFile(file,'CHAT_SCREENSHOT');uploadedTypes.add('CHAT_SCREENSHOT')}
        if(recording){await uploadFile(recording,'CALL_RECORDING');uploadedTypes.add('CALL_RECORDING')}
        submitButton.disabled=uploadedTypes.size===0;
        progress.textContent='已有证据，可以提交退回申请。';
        uploadButton.textContent='证据已上传';
        toast('证据已上传');
      }catch(err){
        uploadButton.disabled=false;
        progress.textContent='部分证据未上传成功，请检查文件后重试。';
        toast(err.message,true);
      }
    };
    submitButton.onclick=async()=>{if(uploadedTypes.size===0){toast('请先上传沟通截图或电话录音',true);return}submitButton.disabled=true;try{await api(`/v1.2/returns/${returnId}/submit`,{method:'POST'});toast('退回申请已提交，等待电销核验');closeSheet();go('returns')}catch(err){submitButton.disabled=false;toast(err.message,true)}};
  });
}
async function returns(){const d=await api(`/v1.2/returns?page=${S.page}&page_size=20`);const list=(d.items||[]).map(x=>item(`退回申诉 · ${readableLabel(x.reason_code,'其他原因')}`,x.status,`<p>提交时间 ${fmt(x.submitted_at||x.created_at)}</p><p>派发编号 ${esc(recordCode(x.assignment_id,'PF'))}</p>`,`<button class="wb-btn" data-return="${x.id}">查看进度</button>`)).join('');shell(`<div class="wb-card-head"><div><h2>退回申诉</h2><p>发起申诉后，平台会根据说明、证据和电话核验结果进行审核。</p></div></div><div class="wb-list">${list||'<div class="wb-empty">暂无退回申诉</div>'}</div>`);document.querySelectorAll('[data-return]').forEach(b=>b.onclick=()=>returnDetail(b.dataset.return));if(S.id){const id=S.id;S.id='';returnDetail(id)}}
async function returnDetail(id){const x=await api(`/v1.2/returns/${id}`),verification=x.verification||{},canSupplement=x.status==='NEED_MORE_EVIDENCE';openSheet('申诉详情',`<div class="wb-detail-grid">${[['退回编号',recordCode(x.id,'TH')],['派发编号',recordCode(x.assignment_id,'PF')],['处理状态',readableLabel(x.status)],['退回原因',readableLabel(x.reason_code,'其他原因')],['电话核验',verification.status?readableLabel(verification.status):'待安排'],['核验结论',verification.conclusion?readableLabel(verification.conclusion):'尚未提交'],['申诉截止',fmt(x.appeal_deadline_at)],['最终结果',returnDecisionSummary(x)]].map(([a,b])=>`<div class="wb-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><div class="wb-card"><h3>申诉说明</h3><p class="wb-muted">${esc(x.description||'暂无说明')}</p></div>${canSupplement?'<button class="wb-btn primary" data-return-evidence="'+esc(x.id)+'">补充证据并重新提交</button>':''}`,()=>document.querySelector('[data-return-evidence]')?.addEventListener('click',()=>evidence(x.id,x.evidence_summary||{})))}
function rewardExplanation(x){if(x.status==='OBSERVING')return `奖励正在确认中，预计结算时间为 ${fmt(x.reward_due_at)}。`;if(x.status==='FROZEN')return `奖励暂缓结算。${rewardReason(x.exception_reason)||'平台复核完成后会更新进度。'}`;if(x.status==='SETTLED')return `奖励已于 ${fmt(x.settled_at)} 结算到账。`;if(x.status==='WAITING_CLAIM')return '客资被领取后会进入奖励确认。';if(x.status==='CANCELLED')return `本次奖励已取消。${rewardReason(x.exception_reason)}`;if(x.status==='REVERSED')return `本次奖励已调整。${rewardReason(x.exception_reason)}`;return '奖励进度以当前页面显示为准。'}
const REWARD_FILTERS=new Set(['SETTLED','OBSERVING','FROZEN']);
async function rewards(){
  const status=REWARD_FILTERS.has(S.id)?S.id:'';
  const d=await api(`/v1.2/supplier-rewards?page=${S.page}&page_size=20${status?`&status=${encodeURIComponent(status)}`:''}`);
  const sum=d.summary||{};
  const list=(d.items||[]).map(x=>item(`${x.reward_points} 奖励积分`,x.status,`<p>当前进度：${esc(readableLabel(x.status))}</p><p>预计结算：${fmt(x.reward_due_at)}</p>`,`<button class="wb-btn" data-reward="${x.id}">查看说明</button>`)).join('');
  const filterNotice=status?`<div class="wb-filter"><span class="wb-status warn">当前筛选：${esc(readableLabel(status))}</span><button class="wb-btn" data-go="rewards">查看全部</button></div>`:'';
  shell(`<section class="wb-hero"><h1>供客奖励</h1><p>点击数字筛选对应进度，快速找到需要关注的奖励。</p><div class="wb-kpis">${metricCard('奖励笔数',sum.total_count||0,{view:'rewards'})}${metricCard('已结算积分',sum.settled_points||0,{view:'rewards',id:'SETTLED'})}${metricCard('确认中积分',sum.observing_points||0,{view:'rewards',id:'OBSERVING'})}${metricCard('暂缓积分',sum.frozen_points||0,{view:'rewards',id:'FROZEN'})}</div></section>${filterNotice}<div class="wb-list">${list||'<div class="wb-empty">暂无对应奖励记录。</div>'}</div>`);
  document.querySelectorAll('[data-reward]').forEach(b=>b.onclick=()=>rewardDetail(b.dataset.reward));
  if(S.id&&!status){const id=S.id;S.id='';rewardDetail(id)}
}
async function rewardDetail(id){const x=await api(`/v1.2/supplier-rewards/${id}`),rule=x.rule_snapshot||{},ratio=(Number(rule.ratio_bps||x.reward_ratio_bps||0)/100).toFixed(2).replace(/\.00$/,'');openSheet('奖励详情',`<div class="wb-detail-grid">${[['当前进度',readableLabel(x.status)],['奖励积分',x.reward_points],['对应客资积分',x.claim_points],['奖励比例',`${ratio}%`],['进入确认',fmt(x.observed_at)],['预计结算',fmt(x.reward_due_at)],['实际到账',fmt(x.settled_at)]].map(([a,b])=>`<div class="wb-detail"><small>${a}</small><b>${esc(b??'--')}</b></div>`).join('')}</div><div class="wb-card"><h3>奖励说明</h3><p class="wb-muted">${esc(rewardExplanation(x))}</p></div><div class="wb-notice">本笔奖励按客资被领取时生效的比例计算，不受后续调整影响。</div>`)}
async function notifications(){const d=await api(`/notifications?page=${S.page}&page_size=30`);const list=(d.items||[]).map(x=>`<article class="wb-item wb-notification ${x.read_at?'':'unread'}" data-msg="${x.id}" data-link="${esc(x.deep_link||'')}"><div class="wb-item-top"><div><h3>${esc(x.title)}</h3><p>${esc(x.body)}</p><p>${fmt(x.created_at)}</p></div>${badge(x.read_at?'READ':'UNREAD')}</div></article>`).join('');shell(`<div class="wb-card-head"><div><h2>消息中心</h2><p>点击消息可查看相关业务。</p></div><button class="wb-btn" data-go="profile">返回我的</button></div><div class="wb-list">${list||'<div class="wb-empty">暂无消息</div>'}</div>`);document.querySelector('[data-go="profile"]')?.addEventListener('click',()=>go('profile'));document.querySelectorAll('[data-msg]').forEach(x=>x.onclick=async()=>{try{await api(`/notifications/${x.dataset.msg}/read`,{method:'POST'})}catch(error){toast(error.message,true);return}const deepLink=safeDeepLink(x.dataset.link);if(deepLink)location.href=deepLink;else render()})}
function renderLogin(message=''){
  zsSetSafeHtml(app, `<main class="wb-main"><section class="wb-hero"><p>加盟商工作台</p><h1>登录后继续</h1><p>负责人和员工只会看到本公司、且符合自身职责的数据。</p></section><section class="wb-card"><form class="wb-form" id="franchise-login-form">${message?`<div class="wb-notice">${esc(message)}</div>`:''}<div class="wb-field"><label for="franchise-username">登录账号</label><input class="wb-input" id="franchise-username" autocomplete="username" required></div><div class="wb-field"><label for="franchise-password">登录密码</label><input class="wb-input" id="franchise-password" type="password" autocomplete="current-password" required></div><button class="wb-btn primary" id="franchise-login-submit" type="submit">登录工作台</button></form></section></main>`);
  document.querySelector('#franchise-login-form').onsubmit=async event=>{
    event.preventDefault();
    const submit=document.querySelector('#franchise-login-submit');
    submit.disabled=true;
    try{
      await api('/auth/login',{method:'POST',body:JSON.stringify({username:document.querySelector('#franchise-username').value.trim(),password:document.querySelector('#franchise-password').value})});
      location.replace('/h5/');
    }catch(error){submit.disabled=false;toast(error.message,true)}
  };
}
async function boot(){try{S.me=await api('/auth/me');const u=new URL(location.href);const fallbackView=defaultWorkbenchView();S.view=u.searchParams.get('view')||fallbackView;S.id=u.searchParams.get('id')||'';S.view=({lead:'leads',assignment:'assignments',return:'returns',reward:'rewards',notification:'notifications'}[S.view]||S.view);if(!VIEWS[S.view]||!canView(S.view))S.view=fallbackView;render()}catch(error){renderLogin(error.message||'请登录后继续')}}boot();
