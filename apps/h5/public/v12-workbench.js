const API='/api/v1',app=document.querySelector('#app'),toastBox=document.querySelector('#toast'),sheet=document.querySelector('#sheet-root');
const S={me:null,view:'home',id:'',page:1};
const LABEL={PENDING:'待审核',PENDING_REVIEW:'待初审',READY_DISPATCH:'待派发',PENDING_CLAIM:'待领取',CLAIMED:'已领取',FOLLOWING:'跟进中',COMPLETED:'已完成',UNCONTACTED:'未联系',CONTACTED:'已联系',INTERESTED:'有意向',NOT_INTERESTED:'无意向',DEAL:'已成交',INVALID:'无效客资',SUBMITTED:'已提交',VERIFYING:'核验中',REVIEWING:'待终审',NEED_MORE_EVIDENCE:'待补证',APPROVED:'已通过',REJECTED:'已驳回',OBSERVING:'观察期',FROZEN:'已冻结',SETTLED:'已结算',CANCELLED:'已取消',REVERSED:'已冲正',WAITING_CLAIM:'待领取'};
const VIEWS={home:['首页','home'],profile:['加盟商设置','building'],leads:['供应客资','inbox'],assignments:['接收客资','hand-claim'],returns:['退回','rotate-ccw'],rewards:['奖励','award'],notifications:['消息','bell']};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>v?new Date(v).toLocaleString('zh-CN'):'--';
const icon=name=>window.ZSIconSystem?.svg(name)||'';
const badge=v=>`<span class="wb-status ${['APPROVED','CLAIMED','SETTLED','COMPLETED'].includes(v)?'ok':['REJECTED','CANCELLED','REVERSED'].includes(v)?'bad':'warn'}">${esc(LABEL[v]||v||'--')}</span>`;
const can=p=>(S.me?.permissions||[]).some(x=>x==='*'||x===p);
const WORKBENCH_REPORT_PERMISSIONS=['assignment.own.read','supplier.lead.manage','supplier.reward.own.read','points.own.read'];
const canAny=permissions=>permissions.some(can);
const canOwnReport=()=>canAny(WORKBENCH_REPORT_PERMISSIONS);
const VIEW_PERMISSION={profile:'company.profile.manage',leads:'supplier.lead.manage',assignments:'assignment.own.read',returns:'return.own.manage',rewards:'supplier.reward.own.read',notifications:'notification.own.read'};
const canView=view=>view==='home'?canOwnReport():Boolean(VIEW_PERMISSION[view]&&can(VIEW_PERMISSION[view]));
function defaultWorkbenchView(){
  if(canView('home'))return 'home';
  if(canView('profile'))return 'profile';
  if(canView('returns'))return 'returns';
  if(canView('notifications'))return 'notifications';
  return 'home';
}
async function api(path,opt={}){const h={...(opt.headers||{})};if(opt.body&&!(opt.body instanceof FormData))h['Content-Type']='application/json';const r=await fetch(API+path,{...opt,headers:h,credentials:'include'});let j={};try{j=await r.json()}catch{}if(!r.ok||j.code!=='OK')throw new Error(j.message||'请求失败');return j.data}
function toast(msg,err=false){toastBox.textContent=msg;toastBox.className=`workbench-toast show ${err?'error':''}`;clearTimeout(toast.t);toast.t=setTimeout(()=>toastBox.className='workbench-toast',2200)}
function closeSheet(){sheet.innerHTML=''}
function openSheet(title,html,bind){zsSetSafeHtml(sheet, `<div class="wb-overlay"><section class="wb-sheet"><div class="wb-sheet-head"><h2>${esc(title)}</h2><button class="wb-btn" id="sheet-close">关闭</button></div>${html}</section></div>`);document.querySelector('#sheet-close').onclick=closeSheet;bind?.()}
function nav(){const hasHome=canView('home');return Object.entries(VIEWS).filter(([view])=>canView(view)&&(view!=='profile'||!hasHome)).slice(0,5).map(([k,[n,i]])=>`<button class="wb-nav ${S.view===k?'active':''}" data-nav="${k}"><span>${icon(i)}</span><span>${n}</span></button>`).join('')}
function shell(body){zsSetSafeHtml(app, `<div class="workbench-shell"><header class="wb-header"><div class="wb-brand"><img class="wb-mark" src="./logo.png" alt="合家美宅"><div><strong>合家美宅</strong><small>${esc(S.me?.display_name||'')}</small></div></div><div class="wb-header-actions">${canView('notifications')?`<button class="wb-icon-btn" id="wb-msg">${icon('bell')}<span>消息</span></button>`:''}<button class="wb-icon-btn" id="wb-refresh">${icon('rotate-ccw')}<span>刷新</span></button></div></header><main class="wb-main">${body}</main><nav class="wb-bottom">${nav()}</nav></div>`);document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>go(b.dataset.nav));const messageButton=document.querySelector('#wb-msg');if(messageButton)messageButton.onclick=()=>go('notifications');document.querySelector('#wb-refresh').onclick=render}
function go(view,id=''){S.view=view;S.id=id;S.page=1;const u=new URL(location.href);u.searchParams.set('view',view);id?u.searchParams.set('id',id):u.searchParams.delete('id');history.replaceState(null,'',u);render()}
function item(title,status,body,actions=''){return `<article class="wb-item"><div class="wb-item-top"><div><h3>${esc(title)}</h3>${body}</div>${badge(status)}</div>${actions?`<div class="wb-actions">${actions}</div>`:''}</article>`}
async function render(){shell('<div class="wb-loading">加载中…</div>');try{if(S.view==='home')await home();else if(S.view==='profile')await profile();else if(S.view==='leads')await leads();else if(S.view==='assignments')await assignments();else if(S.view==='returns')await returns();else if(S.view==='rewards')await rewards();else await notifications()}catch(e){shell(`<div class="wb-error">${esc(e.message)}</div>`);toast(e.message,true)}}
async function home(){const d=await api('/v1.2/reports/own');shell(`<section class="wb-hero"><h1>今天的客资工作</h1><p>供应、领取、退回、奖励和消息集中处理。</p><div class="wb-kpis"><div class="wb-kpi"><b>${d.supplier_leads.total}</b><span>供应客资</span></div><div class="wb-kpi"><b>${d.received_assignments.total}</b><span>接收客资</span></div><div class="wb-kpi"><b>${d.returns.total}</b><span>退回申诉</span></div><div class="wb-kpi"><b>${d.supplier_rewards.points}</b><span>奖励积分</span></div></div></section><div class="wb-grid">${can('supplier.lead.manage')?`<div class="wb-card wb-action-card" data-go="leads"><div class="wb-action-icon">${icon('inbox')}</div><b>供应客资</b><span class="wb-muted">提交与查看初审状态</span></div>`:''}${can('assignment.own.read')?`<div class="wb-card wb-action-card" data-go="assignments"><div class="wb-action-icon">${icon('hand-claim')}</div><b>接收客资</b><span class="wb-muted">领取后解锁联系方式</span></div>`:''}${can('company.profile.manage')?`<div class="wb-card wb-action-card" data-go="profile"><div class="wb-action-icon">${icon('building')}</div><b>加盟商设置</b><span class="wb-muted">申请供应/接收能力与服务区域</span></div>`:''}${can('return.own.manage')?`<div class="wb-card wb-action-card" data-go="returns"><div class="wb-action-icon">${icon('rotate-ccw')}</div><b>退回申诉</b><span class="wb-muted">截图或录音满足其一</span></div>`:''}${can('supplier.reward.own.read')?`<div class="wb-card wb-action-card" data-go="rewards"><div class="wb-action-icon">${icon('award')}</div><b>供应奖励</b><span class="wb-muted">查看观察、冻结与结算</span></div>`:''}</div>`);document.querySelectorAll('[data-go]').forEach(x=>x.onclick=()=>go(x.dataset.go))}
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
    ['能力编码',code],
  ].map(([name,value])=>'<div class="wb-detail"><small>'+esc(name)+'</small><b>'+esc(value||'--')+'</b></div>').join('')+'</div>'+note+'<div class="wb-actions">'+action+'</div></article>';
}
async function profile(){
  if(!can('company.profile.manage')){shell('<div class="wb-error">无权访问加盟商设置</div>');return}
  const [capabilities,areas,cities]=await Promise.all([
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
  const areaCards=areas.length?areas.map(item=>{
    const state=removalPending(item)&&item.active?'待审核移除（当前仍生效）':item.active?'已生效':'未生效';
    const note=item.review_note?'<p>平台说明：'+esc(cleanReviewNote(item.review_note))+'</p>':'';
    return '<article class="wb-item"><div class="wb-item-top"><div><h3>'+esc(item.is_primary_city?'主要城市':'服务区域')+' · '+esc(regionNames[item.region_code]||item.region_code)+'</h3><p>'+esc(item.region_code)+' · '+esc(state)+'</p>'+note+'<p>审核时间 '+fmt(item.reviewed_at)+'</p></div>'+badge(item.review_status)+'</div></article>';
  }).join(''):'<div class="wb-empty service-area-empty">暂无服务区域申请</div>';
  shell('<section class="wb-hero"><h1>加盟商设置</h1><p>供应能力、接收能力和服务区域分别审核。接收能力与区域都生效后，才会进入派单候选。</p><div class="wb-kpis"><div class="wb-kpi"><b>'+approvedCapabilities+'</b><span>已开通能力</span></div><div class="wb-kpi"><b>'+pendingCapabilities+'</b><span>待审能力</span></div><div class="wb-kpi"><b>'+approvedAreas+'</b><span>当前有效区域</span></div><div class="wb-kpi"><b>'+primaryCities.size+'</b><span>主要城市</span></div></div></section><div class="wb-profile-grid"><section class="wb-card"><div class="wb-card-head"><div><h2>公司客资能力</h2><p>供应与接收能力独立申请、独立启停。</p></div></div><div class="wb-list">'+Object.keys(CAPABILITY_META).map(code=>capabilityCard(capabilities,code)).join('')+'</div></section><section class="wb-card"><div class="wb-card-head"><div><h2>服务区域</h2><p>主要城市必须包含在申请中，区县与城市一起审核。</p></div><button class="wb-btn primary" id="service-area-edit">申请/更新</button></div><div class="wb-list" id="service-area-list">'+areaCards+'</div></section></div>');
  document.querySelectorAll('[data-capability-request]').forEach(button=>button.onclick=()=>requestCapability(button));
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
async function leads(){const d=await api(`/v1.2/supplier/leads?page=${S.page}&page_size=20`);const list=(d.items||[]).map(x=>item(x.customer_name,x.status,`<p>${esc(x.phone_masked||'--')} · ${esc(x.city||'')} ${esc(x.district||'')}</p><p>${esc(x.need_summary||'')}</p>`,`<button class="wb-btn" data-lead="${x.id}">详情</button>`)).join('');shell(`<div class="wb-card-head"><div><h2>供应客资</h2><p>初审列表仅展示脱敏手机号。</p></div><a class="wb-btn primary" href="./supplier.html">提交客资</a></div><div class="wb-list">${list||'<div class="wb-empty">暂无客资</div>'}</div>`);document.querySelectorAll('[data-lead]').forEach(b=>b.onclick=()=>leadDetail(b.dataset.lead));if(S.id){const id=S.id;S.id='';leadDetail(id)}}
async function leadDetail(id){const x=await api(`/v1.2/supplier/leads/${id}`);openSheet('客资详情',`<div class="wb-detail-grid">${[['业务ID',x.id],['客户',x.customer_name],['手机号',x.phone_masked],['区域',`${x.city||''} ${x.district||''}`],['状态',LABEL[x.status]||x.status],['初审',LABEL[x.review_status]||x.review_status],['去重',x.duplicate_status]].map(([a,b])=>`<div class="wb-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><div class="wb-card"><h3>需求</h3><p class="wb-muted">${esc(x.need_summary||'--')}</p></div>${x.review_note?`<div class="wb-notice">平台说明：${esc(x.review_note)}</div>`:''}`)}
async function assignments(){const d=await api(`/v1.2/assignments?page=${S.page}&page_size=20`);const list=(d.items||[]).map(x=>item(x.customer_name||x.lead?.customer_name||'客户',x.status,`<p>${esc(x.phone||x.phone_masked||'领取后查看')} · ${esc(x.city||x.lead?.city||'')}</p><p>客资积分 ${x.points_price||0} · 领取截止 ${fmt(x.claim_deadline_at)}</p>`,`<button class="wb-btn" data-assignment="${x.id}">详情</button>${x.status==='PENDING_CLAIM'&&can('assignment.own.claim')?`<button class="wb-btn primary" data-claim="${x.id}">领取</button>`:''}`)).join('');shell(`<div class="wb-card-head"><div><h2>接收客资</h2><p>领取前隐藏明文电话，领取与积分扣减原子执行。</p></div></div><div class="wb-list">${list||'<div class="wb-empty">暂无派发单</div>'}</div>`);document.querySelectorAll('[data-assignment]').forEach(b=>b.onclick=()=>assignmentDetail(b.dataset.assignment));document.querySelectorAll('[data-claim]').forEach(b=>b.onclick=()=>claim(b.dataset.claim));if(S.id){const id=S.id;S.id='';assignmentDetail(id)}}
async function assignmentDetail(id){const [x,followups]=await Promise.all([api(`/v1.2/assignments/${id}`),api(`/followups/assignments/${id}`)]);const history=(followups||[]).map(row=>`<article class="wb-item"><div class="wb-item-top"><div><h3>${esc(LABEL[row.status]||row.status)}</h3><p>${esc(row.note||'无备注')}</p><p>记录时间 ${fmt(row.created_at)}${row.next_followup_at?` · 下次跟进 ${fmt(row.next_followup_at)}`:''}</p></div></div></article>`).join('');const currentFollow=x.current_follow_status||followups?.[0]?.status;const canFollow=['CLAIMED','FOLLOWING'].includes(x.status)&&can('followup.own.manage');openSheet('派发单详情',`<div class="wb-detail-grid">${[['派发单',x.id],['客户',x.customer_name],['电话',x.phone||x.phone_masked||'领取后查看'],['派发状态',LABEL[x.status]||x.status],['客资状态',LABEL[x.lead_status]||x.lead_status],['当前跟进',currentFollow?LABEL[currentFollow]||currentFollow:'暂无'],['客资积分',x.points_price],['申诉截止',fmt(x.appeal_deadline_at)]].map(([a,b])=>`<div class="wb-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><div class="wb-actions">${x.status==='PENDING_CLAIM'&&can('assignment.own.claim')?`<button class="wb-btn primary" id="sheet-claim">领取客资</button>`:''}${canFollow?`<button class="wb-btn primary" id="sheet-followup">新增跟进</button>`:''}${['CLAIMED','FOLLOWING'].includes(x.status)&&can('return.own.manage')?`<button class="wb-btn danger" id="sheet-return">发起退回</button>`:''}</div><div class="wb-card"><h3>跟进历史</h3><div class="wb-list">${history||'<div class="wb-empty">暂无跟进记录</div>'}</div></div>`,()=>{document.querySelector('#sheet-claim')?.addEventListener('click',()=>claim(id));document.querySelector('#sheet-followup')?.addEventListener('click',()=>followupDraft(id));document.querySelector('#sheet-return')?.addEventListener('click',()=>returnDraft(id))})}
async function claim(id){try{await api(`/v1.2/assignments/${id}/claim`,{method:'POST'});toast('领取成功');closeSheet();render()}catch(e){toast(e.message,true)}}
function followupDraft(assignmentId){openSheet('新增跟进',`<form class="wb-form" id="followup-form"><div class="wb-field"><label>跟进状态</label><select class="wb-select" name="status"><option value="CONTACTED">已联系</option><option value="INTERESTED">有意向</option><option value="NOT_INTERESTED">无意向</option><option value="DEAL">已成交</option><option value="INVALID">无效客资</option><option value="UNCONTACTED">未联系</option></select></div><div class="wb-field"><label>跟进备注</label><textarea class="wb-textarea" name="note" maxlength="500" placeholder="填写沟通结果或后续安排"></textarea></div><div class="wb-field"><label>下次跟进时间</label><input class="wb-input" type="datetime-local" name="next_followup_at"><small class="wb-muted">按当前设备本地时间填写，提交时统一转换为标准时间。</small></div><button class="wb-btn primary" id="followup-submit">保存跟进</button></form>`,()=>{const form=document.querySelector('#followup-form'),submitButton=document.querySelector('#followup-submit');let submitting=false;form.onsubmit=async e=>{e.preventDefault();if(submitting)return;submitting=true;submitButton.disabled=true;const fields=Object.fromEntries(new FormData(form));const nextFollowupAt=String(fields.next_followup_at||'').trim();let nextFollowupAtIso=null;if(nextFollowupAt){const parsed=new Date(nextFollowupAt);if(Number.isNaN(parsed.getTime())){submitting=false;submitButton.disabled=false;toast('下次跟进时间格式不正确',true);return}nextFollowupAtIso=new Date(nextFollowupAt).toISOString()}try{await api(`/followups/assignments/${assignmentId}`,{method:'POST',body:JSON.stringify({status:fields.status,note:String(fields.note||'').trim()||null,next_followup_at:nextFollowupAtIso})})}catch(err){submitting=false;submitButton.disabled=false;toast(err.message,true);return}toast('跟进已保存');try{await assignmentDetail(assignmentId)}catch{closeSheet();toast('跟进已保存，请刷新查看',true)}}})}
function returnDraft(assignmentId){openSheet('发起退回申诉',`<form class="wb-form" id="return-form"><div class="wb-field"><label>退回原因</label><select class="wb-select" name="reason_code"><option value="EMPTY_NUMBER">空号/停机</option><option value="OUT_OF_SERVICE_REGION">超出服务区域</option><option value="DUPLICATE_TO_RECEIVER">接收方重复客户</option><option value="NON_HOUSING_CONSULTATION">非建房咨询</option></select></div><div class="wb-field"><label>事实说明</label><textarea class="wb-textarea" name="description" required minlength="5"></textarea></div><button class="wb-btn primary">创建草稿</button></form>`,()=>{document.querySelector('#return-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);try{const x=await api(`/v1.2/returns/assignments/${assignmentId}/draft`,{method:'POST',body:JSON.stringify(Object.fromEntries(f))});closeSheet();evidence(x.id)}catch(err){toast(err.message,true)}}})}
function evidence(returnId){openSheet('上传证据并提交',`<div class="wb-notice">截图或录音任一类型满足即可。</div><form class="wb-form" id="evidence-form"><input class="wb-input" type="file" name="file" required><select class="wb-select" name="evidence_type"><option value="CHAT_SCREENSHOT">截图</option><option value="CALL_RECORDING">录音</option></select><button class="wb-btn">上传证据</button></form><button class="wb-btn primary" id="submit-return" style="margin-top:12px">提交申诉</button>`,()=>{document.querySelector('#evidence-form').onsubmit=async e=>{e.preventDefault();try{await api(`/v1.2/returns/${returnId}/evidence`,{method:'POST',body:new FormData(e.target)});toast('证据已上传')}catch(err){toast(err.message,true)}};document.querySelector('#submit-return').onclick=async()=>{try{await api(`/v1.2/returns/${returnId}/submit`,{method:'POST'});toast('申诉已提交');closeSheet();go('returns')}catch(err){toast(err.message,true)}}})}
async function returns(){const d=await api(`/v1.2/returns?page=${S.page}&page_size=20`);const list=(d.items||[]).map(x=>item(x.id,x.status,`<p>${esc(LABEL[x.reason_code]||x.reason_code)} · ${fmt(x.submitted_at||x.created_at)}</p><p>派发单 ${esc(x.assignment_id)}</p>`,`<button class="wb-btn" data-return="${x.id}">详情</button>`)).join('');shell(`<div class="wb-card-head"><div><h2>退回申诉</h2><p>正常客资不做前置核验，仅申诉进入后置核验。</p></div></div><div class="wb-list">${list||'<div class="wb-empty">暂无申诉</div>'}</div>`);document.querySelectorAll('[data-return]').forEach(b=>b.onclick=()=>returnDetail(b.dataset.return));if(S.id){const id=S.id;S.id='';returnDetail(id)}}
async function returnDetail(id){const x=await api(`/v1.2/returns/${id}`);openSheet('申诉详情',`<div class="wb-detail-grid">${[['申诉ID',x.id],['派发单',x.assignment_id],['状态',LABEL[x.status]||x.status],['原因',LABEL[x.reason_code]||x.reason_code],['核验任务',x.verification_task_id],['申诉截止',fmt(x.appeal_deadline_at)]].map(([a,b])=>`<div class="wb-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><div class="wb-card"><h3>事实说明</h3><p class="wb-muted">${esc(x.description||'--')}</p></div>`)}
async function rewards(){const d=await api(`/v1.2/supplier-rewards?page=${S.page}&page_size=20`);const sum=d.summary||{};const list=(d.items||[]).map(x=>item(`${x.reward_points} 积分`,x.status,`<p>派发单 ${esc(x.assignment_id)}</p><p>应结算 ${fmt(x.reward_due_at)}</p>`,`<button class="wb-btn" data-reward="${x.id}">详情</button>`)).join('');shell(`<section class="wb-hero"><h1>供应商奖励</h1><div class="wb-kpis"><div class="wb-kpi"><b>${sum.total_count||0}</b><span>奖励笔数</span></div><div class="wb-kpi"><b>${sum.settled_points||0}</b><span>已结算</span></div><div class="wb-kpi"><b>${sum.observing_points||0}</b><span>观察中</span></div><div class="wb-kpi"><b>${sum.frozen_points||0}</b><span>冻结中</span></div></div></section><div class="wb-list">${list||'<div class="wb-empty">暂无奖励</div>'}</div>`);document.querySelectorAll('[data-reward]').forEach(b=>b.onclick=()=>rewardDetail(b.dataset.reward));if(S.id){const id=S.id;S.id='';rewardDetail(id)}}
async function rewardDetail(id){const x=await api(`/v1.2/supplier-rewards/${id}`);openSheet('奖励详情',`<div class="wb-detail-grid">${[['奖励ID',x.id],['状态',LABEL[x.status]||x.status],['领取积分',x.claim_points],['奖励积分',x.reward_points],['规则版本',x.rule_version],['到账时间',fmt(x.settled_at)]].map(([a,b])=>`<div class="wb-detail"><small>${a}</small><b>${esc(b||'--')}</b></div>`).join('')}</div><div class="wb-card"><h3>领取时规则快照</h3><pre class="wb-muted">${esc(JSON.stringify(x.rule_snapshot||{},null,2))}</pre></div>`)}
async function notifications(){const d=await api(`/notifications?page=${S.page}&page_size=30`);const list=(d.items||[]).map(x=>`<article class="wb-item wb-notification ${x.read_at?'':'unread'}" data-msg="${x.id}" data-link="${esc(x.deep_link||'')}"><div class="wb-item-top"><div><h3>${esc(x.title)}</h3><p>${esc(x.body)}</p><p>${fmt(x.created_at)}</p></div>${x.read_at?badge('APPROVED'):badge('PENDING_REVIEW')}</div></article>`).join('');shell(`<div class="wb-card-head"><div><h2>消息中心</h2><p>点击消息后标记已读并进入对应业务页面。</p></div></div><div class="wb-list">${list||'<div class="wb-empty">暂无消息</div>'}</div>`);document.querySelectorAll('[data-msg]').forEach(x=>x.onclick=async()=>{try{await api(`/notifications/${x.dataset.msg}/read`,{method:'POST'})}catch{}if(x.dataset.link)location.href=x.dataset.link;else render()})}
async function boot(){try{S.me=await api('/auth/me');const u=new URL(location.href);const fallbackView=defaultWorkbenchView();S.view=u.searchParams.get('view')||fallbackView;S.id=u.searchParams.get('id')||'';S.view=({lead:'leads',assignment:'assignments',return:'returns',reward:'rewards',notification:'notifications'}[S.view]||S.view);if(!VIEWS[S.view]||!canView(S.view))S.view=fallbackView;render()}catch{location.href='./'}}boot();
