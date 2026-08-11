const API = '/api/v1';
const state = { me:null, company:null, summary:null, assignments:[], current:null, files:{screenshots:[],audio:null} };
const app = document.querySelector('#app');
const toastEl = document.querySelector('#toast');

const esc = (value='') => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const fmtDate = value => value ? new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '--';
const money = value => new Intl.NumberFormat('zh-CN').format(Number(value||0));
const uuid = () => crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
const statusLabel = status => ({PENDING_CLAIM:'待领取',CLAIMED:'待跟进',FOLLOWING:'跟进中',RETURN_PENDING:'退回审核中',RETURNED:'已退回',RELEASED:'已释放',EXPIRED:'已过期',COMPLETED:'已完成'}[status] || status || '--');
const statusClass = status => ({PENDING_CLAIM:'pending',CLAIMED:'warning',FOLLOWING:'warning',RETURN_PENDING:'danger',RETURNED:'neutral',RELEASED:'neutral',EXPIRED:'neutral',COMPLETED:'success'}[status] || 'neutral');

function toast(message, type='normal') { toastEl.textContent=message; toastEl.className=`toast show ${type==='error'?'error':''}`; setTimeout(()=>toastEl.className='toast',2600); }
async function api(path, options={}) {
  const headers = {...(options.headers||{})};
  if (!(options.body instanceof FormData) && options.body !== undefined) headers['Content-Type']='application/json';
  const response = await fetch(`${API}${path}`, {...options, credentials:'include', headers});
  let data={}; try{data=await response.json();}catch{data={message:response.statusText};}
  if (!response.ok || data.code !== 'OK') { const err=new Error(data.message||'请求失败'); err.code=data.code; err.details=data.details; throw err; }
  return data.data;
}
function shell(content, active='home', title='客资助手') {
  return `<header class="topbar"><div class="brand"><img src="./logo.png" alt="众墅之家"><div>${esc(title)}<small>让好品牌在乡村生根</small></div></div><button class="icon-btn" data-route="notifications" aria-label="消息">◉</button></header><main class="content">${content}</main>${nav(active)}`;
}
function nav(active){return `<nav class="bottom-nav">${[['home','⌂','首页'],['leads','▤','客资'],['points','◈','积分'],['notifications','◉','消息'],['profile','♙','我的']].map(([r,i,l])=>`<button class="nav-item ${active===r?'active':''}" data-route="${r}"><i>${i}</i>${l}</button>`).join('')}</nav>`;}
function loading(active='home'){zsSetSafeHtml(app, shell(`<div class="skeleton"></div><div class="skeleton" style="margin-top:14px"></div>`,active));bindRoutes();}
function empty(symbol,text){return `<div class="empty"><div class="symbol">${symbol}</div><div>${esc(text)}</div></div>`;}
function bindRoutes(){document.querySelectorAll('[data-route]').forEach(el=>el.addEventListener('click',()=>go(el.dataset.route)));}
function go(route){location.hash=`#/${route}`;}
async function ensureAuth(){
  try{state.me=await api('/auth/me');return true;}catch(err){if(err.code==='AUTH_REQUIRED'||err.code==='AUTH_INVALID'){renderLogin();return false;}throw err;}
}

function renderLogin(){
  const params=new URLSearchParams(location.hash.split('?')[1]||''); const invite=params.get('invite')||'';
  app.innerHTML=`<section class="login-page"><div class="login-logo"><img src="./logo.png" alt="众墅之家"><h1>加盟商客资助手</h1><p>微信内打开 · 无需安装 · 点击即处理</p></div><div class="login-panel"><button class="btn btn-primary btn-block" id="wechat-login">微信授权登录</button>${invite?'<p class="help">已识别专属加盟商邀请，授权后将自动绑定。</p>':'<p class="help">请通过平台发送的专属邀请链接在微信内进入。</p>'}</div></section>`;
  document.querySelector('#wechat-login').onclick=()=>{if(!invite){toast('请使用平台发出的专属邀请链接','error');return;} location.href=`${API}/auth/wechat/start?invite=${encodeURIComponent(invite)}&return_url=${encodeURIComponent('/h5/#/home')}`;};
}

async function renderHome(){
  loading('home'); if(!await ensureAuth())return;
  const [summary,account,assignments]=await Promise.all([
    api('/dashboard/summary'),
    api(`/points/accounts/${state.me.company_id}`),
    api('/dispatch/assignments?page=1&page_size=3')
  ]);
  state.summary=summary;state.company=account;state.assignments=assignments.items;
  const b=summary.business||{};
  zsSetSafeHtml(app, shell(`<h1 class="page-title">您好，${esc(state.me.display_name)}</h1><p class="subtitle">${esc(account.company_name||'加盟商')} · ${esc(account.level_code||'V1')} 会员</p><section class="hero"><div class="row"><div><div class="eyebrow">当前可用积分</div><div class="balance">${money(account.balance)}<span> 分</span></div><div class="eyebrow">待领取预计占用 ${money(account.pending_claim_points)} 分</div></div><button class="btn btn-gold" data-route="points">积分明细</button></div></section><section class="grid metrics"><div class="metric"><span>待领取</span><b>${b.pending_claim||0}</b></div><div class="metric"><span>待跟进</span><b>${b.claimed||0}</b></div><div class="metric"><span>退回审核</span><b>${b.return_pending||0}</b></div><div class="metric"><span>已完成</span><b>${b.completed||0}</b></div></section><section class="card"><div class="card-title"><h3>待处理客资</h3><a data-route="leads">查看全部 ›</a></div><div class="list">${assignments.items.length?assignments.items.map(assignmentCard).join(''):empty('✓','当前没有待处理客资')}</div></section><section class="card"><div class="card-title"><h3>使用提醒</h3></div><p class="subtitle" style="margin:0">派发后请尽快领取。领取成功即扣除对应积分，并解锁完整联系方式；发现不合格客资需在规定时间内上传聊天截图和电话录音。</p></section>`,'home'));
  bindRoutes();bindAssignmentCards();
}
function assignmentCard(x){const l=x.lead_snapshot||{};return `<article class="lead-card" data-assignment="${x.id}"><div class="line"><h3>${esc(l.customer_name||'客户')}</h3><span class="badge badge-${statusClass(x.status)}">${statusLabel(x.status)}</span></div><p>${esc(l.city||'')} ${esc(l.district||'')} · ${esc(l.category_code||'客资')}<br>${fmtDate(x.assigned_at)}</p><div class="line" style="margin-top:10px"><span class="price">${money(x.points_price)} 积分</span><span>查看 ›</span></div></article>`;}
function bindAssignmentCards(){document.querySelectorAll('[data-assignment]').forEach(el=>el.onclick=()=>go(`lead/${el.dataset.assignment}`));}

async function renderLeads(){
  loading('leads');if(!await ensureAuth())return;
  const hash=location.hash;const query=new URLSearchParams(hash.split('?')[1]||'');const filter=query.get('status')||'';
  const data=await api(`/dispatch/assignments?page=1&page_size=100${filter?`&status=${encodeURIComponent(filter)}`:''}`);state.assignments=data.items;
  zsSetSafeHtml(app, shell(`<h1 class="page-title">我的客资</h1><p class="subtitle">仅显示派发给当前加盟商公司的客资</p><div class="tabs">${[['','全部'],['PENDING_CLAIM','待领取'],['CLAIMED','待跟进'],['FOLLOWING','跟进中'],['RETURN_PENDING','退回中'],['COMPLETED','已完成']].map(([v,l])=>`<button class="tab ${filter===v?'active':''}" data-filter="${v}">${l}</button>`).join('')}</div><div class="list">${data.items.length?data.items.map(assignmentCard).join(''):empty('⌕','暂无符合条件的客资')}</div>`,'leads','我的客资'));
  bindRoutes();bindAssignmentCards();document.querySelectorAll('[data-filter]').forEach(el=>el.onclick=()=>{location.hash=`#/leads${el.dataset.filter?`?status=${el.dataset.filter}`:''}`});
}

async function renderLead(id){
  loading('leads');if(!await ensureAuth())return;
  const detail=await api(`/claims/assignments/${id}`);state.current=detail;const l=detail.lead||{};const canClaim=detail.status==='PENDING_CLAIM';const unlocked=l.contact_unlocked;
  zsSetSafeHtml(app, shell(`<button class="icon-btn" data-history-back>‹ 返回</button><h1 class="page-title">客资详情</h1><section class="hero"><div class="eyebrow">领取所需积分</div><div class="balance">${money(detail.points_price)}<span> 分</span></div><div class="eyebrow">可用积分 ${money(detail.points.available)} 分</div></section><section class="card"><div class="card-title"><h3>客户信息</h3><span class="badge badge-${statusClass(detail.status)}">${statusLabel(detail.status)}</span></div><dl class="detail-list"><div class="detail-row"><dt>客户姓名</dt><dd>${esc(l.customer_name)}</dd></div><div class="detail-row"><dt>所在地区</dt><dd>${esc(l.city)} ${esc(l.district)}</dd></div><div class="detail-row"><dt>业务类型</dt><dd>${esc(l.category_code||'--')}</dd></div><div class="detail-row"><dt>需求来源</dt><dd>${esc(l.source_channel||'--')}</dd></div><div class="detail-row"><dt>预算范围</dt><dd>${l.budget_min?`${money(l.budget_min)} - ${money(l.budget_max)} 元`:'--'}</dd></div><div class="detail-row"><dt>需求描述</dt><dd>${esc(l.need_summary||'--')}</dd></div><div class="detail-row"><dt>联系电话</dt><dd><strong>${esc(unlocked?(l.phone||l.phone_masked):l.phone_masked)}</strong>${unlocked?'':'（领取后解锁）'}</dd></div></dl>${unlocked?`<div class="phone-action"><a class="btn btn-primary" href="tel:${esc(l.phone)}">拨打电话</a><button class="btn btn-outline" id="copy-phone">复制号码</button></div>`:''}</section>${canClaim?`<section class="card"><h3>领取须知</h3><p class="subtitle">领取成功后将立即扣除 ${money(detail.points_price)} 积分。请在 48 小时内完成首次跟进反馈。</p><button class="btn btn-primary btn-block" id="claim-btn" ${detail.points.available<detail.points_price?'disabled':''}>${detail.points.available<detail.points_price?'积分不足，暂不可领取':`立即领取（扣 ${money(detail.points_price)} 积分）`}</button></section>`:`<section class="card"><div class="grid"><button class="btn btn-primary" id="follow-btn">提交跟进</button><button class="btn btn-danger" id="return-btn">申请退回</button></div><div id="follow-history"></div></section>`}<section class="card"><div class="card-title"><h3>时间节点</h3></div><div class="timeline"><div class="timeline-item"><b>派发时间</b><br><small>${fmtDate(detail.assigned_at)}</small></div>${detail.claimed_at?`<div class="timeline-item"><b>领取时间</b><br><small>${fmtDate(detail.claimed_at)}</small></div>`:''}<div class="timeline-item"><b>${canClaim?'领取截止':'首次跟进要求'}</b><br><small>${fmtDate(canClaim?detail.expires_at:detail.first_followup_due_at)}</small></div></div></section>`,'leads','客资详情'));
  bindRoutes();
  if(document.querySelector('#claim-btn'))document.querySelector('#claim-btn').onclick=()=>confirmClaim(id,detail.points_price);
  if(document.querySelector('#copy-phone'))document.querySelector('#copy-phone').onclick=async()=>{await navigator.clipboard.writeText(l.phone||'');toast('号码已复制');};
  if(document.querySelector('#follow-btn')){document.querySelector('#follow-btn').onclick=()=>showFollowModal(id);loadFollowups(id);}
  if(document.querySelector('#return-btn'))document.querySelector('#return-btn').onclick=()=>go(`return/${id}`);
}
async function confirmClaim(id,points){
  document.body.insertAdjacentHTML('beforeend',`<div class="modal-backdrop" id="claim-modal"><div class="modal"><h2>确认领取这条客资？</h2><p class="subtitle">领取后将扣除 <b>${money(points)}</b> 积分，并立即显示完整联系方式。</p><button class="btn btn-primary btn-block" id="confirm-claim">确认领取</button><button class="btn btn-outline btn-block" style="margin-top:10px" id="cancel-claim">暂不领取</button></div></div>`);
  document.querySelector('#cancel-claim').onclick=()=>document.querySelector('#claim-modal').remove();
  document.querySelector('#confirm-claim').onclick=async()=>{try{await api(`/claims/assignments/${id}`,{method:'POST',body:JSON.stringify({idempotency_key:`h5-${uuid()}`})});document.querySelector('#claim-modal').remove();toast('领取成功，完整联系方式已解锁');renderLead(id);}catch(e){toast(e.message,'error');}};
}
async function loadFollowups(id){try{const list=await api(`/followups/assignments/${id}`);const el=document.querySelector('#follow-history');if(el)zsSetSafeHtml(el, list.length?`<div class="timeline">${list.map(x=>`<div class="timeline-item"><b>${esc(x.status)}</b><br><span>${esc(x.note||'')}</span><br><small>${fmtDate(x.created_at)}</small></div>`).join('')}</div>`:'<p class="subtitle">暂无跟进记录</p>');}catch(e){toast(e.message,'error');}}
function showFollowModal(id){
  document.body.insertAdjacentHTML('beforeend',`<div class="modal-backdrop" id="follow-modal"><div class="modal"><h2>提交跟进反馈</h2><div class="form-group"><label>跟进状态</label><select class="select" id="follow-status"><option value="CONTACTED">已联系</option><option value="INTERESTED">意向客户</option><option value="NOT_INTERESTED">无意向</option><option value="DEAL">已成交</option><option value="INVALID">无效</option></select></div><div class="form-group"><label>跟进说明</label><textarea class="textarea" id="follow-note" placeholder="记录沟通结果和下一步计划"></textarea></div><button class="btn btn-primary btn-block" id="save-follow">保存反馈</button><button class="btn btn-outline btn-block" style="margin-top:10px" id="cancel-follow">取消</button></div></div>`);
  document.querySelector('#cancel-follow').onclick=()=>document.querySelector('#follow-modal').remove();
  document.querySelector('#save-follow').onclick=async()=>{try{await api(`/followups/assignments/${id}`,{method:'POST',body:JSON.stringify({status:document.querySelector('#follow-status').value,note:document.querySelector('#follow-note').value||null,next_followup_at:null})});document.querySelector('#follow-modal').remove();toast('跟进已保存');renderLead(id);}catch(e){toast(e.message,'error');}};
}

async function renderReturn(id){
  loading('leads');if(!await ensureAuth())return;
  const detail=await api(`/claims/assignments/${id}`);state.current=detail;
  zsSetSafeHtml(app, shell(`<button class="icon-btn" data-history-back>‹ 返回</button><h1 class="page-title">申请退回</h1><p class="subtitle">必须同时上传沟通截图和电话录音，平台审核通过后才返还积分。</p><div class="stepper"><div class="step active"><i>1</i>选择原因</div><div class="step active"><i>2</i>上传证据</div><div class="step"><i>3</i>提交审核</div></div><section class="card"><div class="form-group"><label>退回原因 *</label><select class="select" id="return-reason"><option value="EMPTY_NUMBER">空号/停机/无法接通</option><option value="DUPLICATE">重复客户</option><option value="REGION_WRONG">地区错误</option><option value="NON_TARGET">非目标客户</option><option value="INFO_ERROR">关键信息错误</option></select></div><div class="form-group"><label>补充说明 *</label><textarea class="textarea" id="return-description" placeholder="请具体说明核验过程、客户反馈及判断依据"></textarea></div><div class="form-group"><label>聊天/沟通截图 *</label><div class="upload"><input type="file" id="screenshot-files" accept="image/png,image/jpeg,image/webp" multiple><p class="help">至少1张，最多5张，单张不超过5MB</p></div></div><div class="form-group"><label>电话录音 *</label><div class="upload"><input type="file" id="audio-file" accept="audio/*,.m4a,.mp3,.wav,.aac"><p class="help">请上传手机或合规工具生成的录音，单个不超过20MB</p></div></div><button class="btn btn-primary btn-block" id="submit-return">提交退回申请</button></section>`,'leads','退回申请'));bindRoutes();
  document.querySelector('#submit-return').onclick=()=>submitReturn(id);
}
async function submitReturn(id){
  const description=document.querySelector('#return-description').value.trim();const screenshots=[...document.querySelector('#screenshot-files').files];const audio=document.querySelector('#audio-file').files[0];
  if(description.length<3||!screenshots.length||!audio){toast('请完整填写说明并上传截图和电话录音','error');return;}
  try{
    const draft=await api(`/returns/assignments/${id}/draft`,{method:'POST',body:JSON.stringify({reason_code:document.querySelector('#return-reason').value,description})});
    for(const file of screenshots){const form=new FormData();form.append('evidence_type','CHAT_SCREENSHOT');form.append('file',file);await api(`/returns/${draft.id}/evidence`,{method:'POST',body:form});}
    const form=new FormData();form.append('evidence_type','CALL_RECORDING');form.append('file',audio);await api(`/returns/${draft.id}/evidence`,{method:'POST',body:form});
    await api(`/returns/${draft.id}/submit`,{method:'POST'});toast('退回申请已提交，等待管理员审核');go('leads?status=RETURN_PENDING');
  }catch(e){toast(e.message,'error');}
}

async function renderPoints(){
  loading('points');if(!await ensureAuth())return;
  const [account,ledgers,packages]=await Promise.all([api(`/points/accounts/${state.me.company_id}`),api(`/points/ledgers?company_id=${state.me.company_id}&page=1&page_size=50`),api('/points/packages')]);
  zsSetSafeHtml(app, shell(`<h1 class="page-title">积分中心</h1><p class="subtitle">线下付款后，由平台授权管理员人工充值积分</p><section class="hero"><div class="eyebrow">当前积分余额</div><div class="balance">${money(account.balance)}<span> 分</span></div><div class="row"><span>会员等级 ${esc(account.level_code)}</span><span>可派发积分 ${money(account.available_for_dispatch)}</span></div></section><section class="card"><div class="card-title"><h3>充值档位参考</h3></div>${packages.map(p=>`<div class="lead-card"><div class="line"><b>${esc(p.name)}</b><span class="badge badge-warning">${esc(p.level_code)}</span></div><p>线下实收 ¥${money(p.cash_amount_cents/100)} · 到账 ${money(p.base_points+p.bonus_points)} 积分</p></div>`).join('')}<p class="help">以上为系统配置档位，实际付款请联系平台并以线下确认结果为准。</p></section><section class="card"><div class="card-title"><h3>积分流水</h3></div><div class="list">${ledgers.items.length?ledgers.items.map(x=>`<div class="lead-card"><div class="line"><b>${esc({RECHARGE:'充值入账',CLAIM:'领取扣分',RETURN:'退回返分',ADJUST:'人工调整',REVERSAL:'冲正'}[x.type]||x.type)}</b><span class="price" style="color:${x.delta>=0?'var(--success)':'var(--ink)'}">${x.delta>=0?'+':''}${money(x.delta)}</span></div><p>${fmtDate(x.created_at)} · 余额 ${money(x.balance_after)}</p></div>`).join(''):empty('◈','暂无积分流水')}</div></section>`,'points','积分中心'));bindRoutes();
}

async function renderNotifications(){
  loading('notifications');if(!await ensureAuth())return;
  const data=await api('/notifications?page=1&page_size=100');
  zsSetSafeHtml(app, shell(`<h1 class="page-title">消息中心</h1><p class="subtitle">业务消息长期留痕，微信通知失败时仍可在此查看</p><div class="list">${data.items.length?data.items.map(x=>`<article class="lead-card" data-notification="${x.id}" data-link="${esc(x.deep_link||'')}"><div class="line"><h3>${esc(x.title)}</h3>${x.read_at?'':'<span class="badge badge-danger">未读</span>'}</div><p>${esc(x.body)}</p><p>${fmtDate(x.created_at)}</p></article>`).join(''):empty('◉','暂无消息')}</div>`,'notifications','消息中心'));bindRoutes();document.querySelectorAll('[data-notification]').forEach(el=>el.onclick=async()=>{try{await api(`/notifications/${el.dataset.notification}/read`,{method:'POST'});if(el.dataset.link){location.href=el.dataset.link;}else renderNotifications();}catch(e){toast(e.message,'error');}});
}

async function renderProfile(){
  loading('profile');if(!await ensureAuth())return; const account=await api(`/points/accounts/${state.me.company_id}`);
  zsSetSafeHtml(app, shell(`<h1 class="page-title">我的</h1><section class="card"><div class="brand"><img src="./logo.png"><div>${esc(state.me.display_name)}<small>${esc(account.company_name)}</small></div></div><dl class="detail-list" style="margin-top:15px"><div class="detail-row"><dt>会员等级</dt><dd>${esc(account.level_code)}</dd></div><div class="detail-row"><dt>公司编号</dt><dd>${esc(state.me.company_id)}</dd></div><div class="detail-row"><dt>登录方式</dt><dd>微信授权</dd></div></dl></section><section class="card"><button class="btn btn-outline btn-block" data-route="notifications">消息中心</button><button class="btn btn-outline btn-block" style="margin-top:10px" data-route="points">积分明细</button><button class="btn btn-danger btn-block" style="margin-top:10px" id="logout">退出登录</button></section><section class="card"><h3>隐私与安全</h3><p class="subtitle">完整客户联系方式仅在成功领取后显示；退回证据采用私有存储和短时授权访问。</p></section>`,'profile','个人中心'));bindRoutes();document.querySelector('#logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'});}finally{state.me=null;location.hash='#/login';renderLogin();}};
}

async function renderLink(token){loading('leads');if(!await ensureAuth())return;try{const data=await api(`/claims/resolve-link?token=${encodeURIComponent(token)}`);go(`lead/${data.assignment_id}`);}catch(e){zsSetSafeHtml(app, shell(empty('!','链接已失效或该客资已被回收'),'leads','链接失效'));bindRoutes();toast(e.message,'error');}}
async function route(){
  const raw=location.hash.replace(/^#\/?/,'')||'home';const [path]=raw.split('?');const parts=path.split('/');
  try{
    if(parts[0]==='login')return renderLogin();
    if(parts[0]==='home')return renderHome();
    if(parts[0]==='leads'&&parts[1])return renderLead(parts[1]);
    if(parts[0]==='lead'&&parts[1])return renderLead(parts[1]);
    if(parts[0]==='return'&&parts[1])return renderReturn(parts[1]);
    if(parts[0]==='link'&&parts[1])return renderLink(parts.slice(1).join('/'));
    if(parts[0]==='leads')return renderLeads();
    if(parts[0]==='points')return renderPoints();
    if(parts[0]==='notifications')return renderNotifications();
    if(parts[0]==='profile')return renderProfile();
    go('home');
  }catch(e){console.error(e);toast(e.message||'页面加载失败','error');zsSetSafeHtml(app, shell(empty('!','页面加载失败，请稍后重试'),'home'));bindRoutes();}
}
window.addEventListener('hashchange',route);route();
