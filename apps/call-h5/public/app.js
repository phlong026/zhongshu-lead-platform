const API = '/api/v1';
const app = document.querySelector('#app');
const toastEl = document.querySelector('#toast');

let me = null;

const TASK_KIND = {
  PRE_DISPATCH: {
    label: '前置核验',
    listPath: '/v1.2/pre-dispatch-verifications/tasks',
    detailPath: (id) => `/v1.2/pre-dispatch-verifications/tasks/${encodeURIComponent(id)}`,
    conclusions: {
      QUALIFIED: '信息合格', INFO_INCOMPLETE: '信息不全', UNVERIFIABLE: '无法核验', INVALID: '明确无效', DUPLICATE: '重复客资',
    },
  },
  RETURN: {
    label: '退回核验',
    listPath: '/v1.2/return-verifications/tasks',
    detailPath: (id) => `/v1.2/return-verifications/tasks/${encodeURIComponent(id)}`,
    conclusions: { SUPPORT_RETURN: '支持退回', DOES_NOT_SUPPORT_RETURN: '不支持退回', INCONCLUSIVE: '信息不足' },
  },
};

const TELESALES_HOME_CONTRACT = {
  metrics: ['待开始', '核验中', '已提交'],
  primaryActions: ['开始核验', '继续核验'],
  detail: ['一键拨号', '核验说明', '填写结果'],
};
const contactLabels = {
  CONNECTED: '已接通', NO_ANSWER: '无人接听', EMPTY_NUMBER: '空号', OUT_OF_SERVICE: '停机', WRONG_PERSON: '非本人', REFUSED: '拒接/拒访', OTHER: '其他',
};
const returnReasonLabels = {
  EMPTY_NUMBER: '空号或停机', OUT_OF_SERVICE_REGION: '超出服务区域', DUPLICATE_TO_RECEIVER: '接收方重复客资', NON_HOUSING_CONSULTATION: '非建房装修咨询',
};
const statusLabels = { ASSIGNED: '待开始', IN_PROGRESS: '核验中', SUBMITTED: '已提交' };

const esc = (value = '') => String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
const icon = (name) => window.ZSIconSystem?.svg?.(name) || '';
const fmt = (value) => value ? new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '--';
const statusLabel = (value) => statusLabels[value] || '待确认';
const statusClass = (value) => value === 'SUBMITTED' ? 'done' : value === 'IN_PROGRESS' ? 'doing' : 'pending';
const evidenceCount = (request = {}) => Object.values(request.evidence_summary || {}).reduce((sum, count) => sum + Number(count || 0), 0);

function toast(message, type = '') {
  toastEl.textContent = message;
  toastEl.className = `toast show ${type}`;
  setTimeout(() => { toastEl.className = 'toast'; }, 2400);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(API + path, { ...options, headers, credentials: 'include' });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.code !== 'OK') {
    const error = new Error(payload.message || '请求失败');
    error.code = payload.code;
    throw error;
  }
  return payload.data;
}

function taskPath(kind, taskId, action = '') {
  const root = TASK_KIND[kind].detailPath(taskId);
  return action ? `${root}/${action}` : root;
}

function nav(active) {
  const items = [['home', 'home', '首页'], ['verify', 'phone', '核验'], ['records', 'history', '记录'], ['profile', 'user', '我的']];
  return `<nav class="bottom" aria-label="底部导航">${items.map(([route, iconName, label]) => `<button class="nav ${active === route ? 'active' : ''}" data-route="${route}"><i>${icon(iconName)}</i><span>${label}</span></button>`).join('')}</nav>`;
}

function shell(content, active = 'home', title = '电销工作台') {
  return `<div class="shell"><header class="top"><div class="brand"><img src="./logo.png" alt="合家美宅"><div>合家美宅<small>${esc(title)} · 仅处理运营派发任务</small></div></div><button class="btn small outline icon-btn" id="refresh">${icon('rotate-ccw')}<span>刷新</span></button></header><main class="content">${content}</main>${nav(active)}</div>`;
}

function bind() {
  document.querySelectorAll('[data-route]').forEach((node) => { node.onclick = () => go(node.dataset.route); });
  document.querySelectorAll('[data-history-back]').forEach((node) => { node.onclick = () => (history.length > 1 ? history.back() : go('verify')); });
  document.querySelector('#refresh')?.addEventListener('click', route);
}

function go(routeName) {
  const next = `#/${routeName}`;
  if (location.hash === next) route(); else location.hash = next;
}

function emptyState(title, description) {
  return `<div class="empty"><b>${esc(title)}</b><span>${esc(description)}</span></div>`;
}

async function auth() {
  try {
    me = await api('/auth/me');
    if (!me.roles.includes('TELESALES')) throw new Error('当前账号不是电销人员');
    return true;
  } catch (error) {
    renderLogin(error.code ? '' : error.message);
    return false;
  }
}

function renderLogin(message = '') {
  zsSetSafeHtml(app, `<section class="login"><div class="login-brand"><span class="login-kicker">合家美宅 · 内部登录</span><img src="./logo.png" alt="合家美宅"><h1>电销工作台</h1><p>仅显示运营人员已派发给您的前置核验和退回事实核验任务。</p></div><div class="panel login-card"><div class="login-card-head"><span>内部账号登录</span><h2>欢迎回来</h2><p>登录后只进入电销任务工作台。</p></div>${message ? `<p class="error-text">${esc(message)}</p>` : ''}<form id="call-login-form" novalidate><div class="login-field"><label for="user">登录账号</label><div class="login-input-wrap"><i>${icon('user')}</i><input id="user" name="username" autocomplete="username" placeholder="请输入电销账号" required></div></div><div class="login-field"><label for="pass">登录密码</label><div class="login-input-wrap"><i>${icon('lock')}</i><input id="pass" name="password" type="password" autocomplete="current-password" placeholder="请输入登录密码" required></div></div><button id="login" class="btn primary block login-submit" type="submit">登录工作台</button></form><p class="login-security">完整号码仅在您开始本人任务后显示；拨号必须由您主动点击。</p></div></section>`);
  document.querySelector('#call-login-form').onsubmit = async (event) => {
    event.preventDefault();
    const button = document.querySelector('#login');
    button.disabled = true;
    try {
      await api('/auth/login', { method: 'POST', body: JSON.stringify({ username: document.querySelector('#user').value.trim(), password: document.querySelector('#pass').value }) });
      location.hash = '#/home';
      await route();
    } catch (error) {
      button.disabled = false;
      toast(error.message, 'error');
    }
  };
}

async function loadTasks(status = '') {
  const query = `?page=1&page_size=200${status ? `&status=${encodeURIComponent(status)}` : ''}`;
  const [preDispatch, returns] = await Promise.all([
    api(`${TASK_KIND.PRE_DISPATCH.listPath}${query}`),
    api(`${TASK_KIND.RETURN.listPath}${query}&mine=true`),
  ]);
  const rank = { IN_PROGRESS: 0, ASSIGNED: 1, SUBMITTED: 2 };
  return [
    ...(preDispatch.items || []).map((item) => ({ ...item, task_kind: 'PRE_DISPATCH' })),
    ...(returns.items || []).map((item) => ({ ...item, task_kind: 'RETURN' })),
  ].sort((left, right) => (rank[left.status] ?? 9) - (rank[right.status] ?? 9) || String(right.assigned_at || right.created_at || '').localeCompare(String(left.assigned_at || left.created_at || '')));
}

function metric(items, statuses) { return items.filter((item) => statuses.includes(item.status)).length; }

function taskDescription(task) {
  return task.task_kind === 'PRE_DISPATCH' ? task.lead?.need_summary || '请核对客户资料完整性与真实性。' : task.return_request?.description || '请结合退回申请和已提交证据核验事实。';
}

function taskCard(task) {
  const lead = task.lead || {};
  const request = task.return_request || {};
  const typeFact = task.task_kind === 'RETURN' ? `退回原因：${returnReasonLabels[request.reason_code] || '待确认'} · 证据 ${evidenceCount(request)} 份` : '资料不全，等待电话事实核验';
  return `<article class="task" data-task-kind="${task.task_kind}" data-task="${task.id}" tabindex="0"><div class="row"><h3>${esc(lead.customer_name || '待核验客户')}</h3><span class="badge ${statusClass(task.status)}">${esc(statusLabel(task.status))}</span></div><p class="task-meta">${esc(TASK_KIND[task.task_kind].label)} · ${esc(lead.city || '')} ${esc(lead.district || '')}</p><dl class="task-facts"><div><dt>任务说明</dt><dd>${esc(typeFact)}</dd></div><div><dt>派发时间</dt><dd>${fmt(task.assigned_at)}</dd></div></dl><p>${esc(taskDescription(task))}</p></article>`;
}

function bindTaskCards() {
  document.querySelectorAll('[data-task]').forEach((node) => {
    const open = () => go(`task/${node.dataset.taskKind}/${node.dataset.task}`);
    node.onclick = open;
    node.onkeydown = (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); } };
  });
}

async function home() {
  if (!await auth()) return;
  const tasks = await loadTasks();
  const actionable = tasks.filter((item) => item.status !== 'SUBMITTED');
  const hasDoing = actionable.some((item) => item.status === 'IN_PROGRESS');
  zsSetSafeHtml(app, shell(`<section class="home-title"><p class="eyebrow">个人任务工作台</p><h1>您好，${esc(me.display_name)}</h1><p class="muted">待办仅来自运营派发；您提交事实结论后，由运营决定后续处理。</p></section><section class="hero"><div><small>当前待办</small><strong>${actionable.length}</strong><span>待开始和核验中的本人任务</span></div><button class="btn gold" data-route="verify">${icon(hasDoing ? 'user-check' : 'phone')}<span>${hasDoing ? '继续核验' : '开始核验'}</span></button></section><section class="metrics" aria-label="个人任务统计"><button type="button" class="metric" data-route="verify?status=ASSIGNED"><span>待开始</span><b>${metric(tasks, ['ASSIGNED'])}</b></button><button type="button" class="metric" data-route="verify?status=IN_PROGRESS"><span>核验中</span><b>${metric(tasks, ['IN_PROGRESS'])}</b></button><button type="button" class="metric" data-route="records"><span>已提交</span><b>${metric(tasks, ['SUBMITTED'])}</b></button></section><section class="card"><div class="row section-head"><h2>待办</h2><button class="btn small outline" data-route="verify">全部</button></div>${actionable.length ? actionable.slice(0, 5).map(taskCard).join('') : emptyState('暂无待办任务', '运营派发新的核验任务后会显示在这里。')}</section>`));
  bind();
  bindTaskCards();
}

async function verify() {
  if (!await auth()) return;
  const query = new URLSearchParams(location.hash.split('?')[1] || '');
  const status = query.get('status') || '';
  const items = (await loadTasks(status)).filter((item) => item.status !== 'SUBMITTED');
  zsSetSafeHtml(app, shell(`<h1>核验任务</h1><div class="filters" role="tablist">${[['', '全部'], ['ASSIGNED', '待开始'], ['IN_PROGRESS', '核验中']].map(([value, label]) => `<button class="btn small ${status === value ? 'primary' : 'outline'}" data-filter="${value}">${label}</button>`).join('')}</div>${items.length ? items.map(taskCard).join('') : emptyState('暂无符合条件的任务', '这里只显示运营已派发给您的任务。')}`, 'verify', '核验任务'));
  bind();
  bindTaskCards();
  document.querySelectorAll('[data-filter]').forEach((node) => { node.onclick = () => { location.hash = `#/verify${node.dataset.filter ? `?status=${node.dataset.filter}` : ''}`; }; });
}

async function records() {
  if (!await auth()) return;
  const items = (await loadTasks('SUBMITTED')).filter((item) => item.status === 'SUBMITTED');
  zsSetSafeHtml(app, shell(`<h1>核验记录</h1><p class="muted">已提交的内容只保留事实结论，后续业务处置由运营人员完成。</p>${items.length ? items.map(taskCard).join('') : emptyState('暂无已提交记录', '完成核验并提交后，记录会保留在这里。')}`, 'records', '核验记录'));
  bind();
  bindTaskCards();
}

function taskFacts(kind, data) {
  const lead = data.lead || {};
  if (kind === 'PRE_DISPATCH') return [['任务类型', '前置核验'], ['客户需求', lead.need_summary || '--'], ['下一步', data.status === 'SUBMITTED' ? '等待运营处置' : '完成电话事实核验']];
  const request = data.return_request || {};
  return [['任务类型', '退回核验'], ['退回原因', returnReasonLabels[request.reason_code] || '待确认'], ['证据数量', `${evidenceCount(request)} 份`], ['下一步', data.status === 'SUBMITTED' ? '等待运营终审' : '完成退回事实核验']];
}

function taskForm(kind) {
  const conclusions = TASK_KIND[kind].conclusions;
  return `<section class="card" id="result-form"><h2>填写结果</h2><div class="form"><label>联系结果 *</label><select id="contact_result" class="select">${Object.entries(contactLabels).map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select></div><div class="form"><label>事实结论 *</label><div class="radio-grid">${Object.entries(conclusions).map(([value, label], index) => `<label class="choice"><input type="radio" name="conclusion" value="${value}" ${index === 0 ? 'checked' : ''}> ${label}</label>`).join('')}</div></div><div class="form"><label>核验备注 *</label><textarea id="note" class="textarea" placeholder="记录客户说明和核验依据"></textarea></div><button id="submit" class="btn primary block">提交核验结果</button></section>`;
}

async function task(kind, id) {
  if (!TASK_KIND[kind] || !await auth()) return;
  const data = await api(taskPath(kind, id));
  const lead = data.lead || {};
  const details = taskFacts(kind, data).map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('');
  const action = data.status === 'ASSIGNED' ? `<section class="card"><h2>开始核验</h2><p class="muted">该任务已由运营派发给您。开始后可查看完整手机号；这不是自主领取。</p><button class="btn primary block" id="start">开始核验</button></section>` : data.status === 'IN_PROGRESS' ? taskForm(kind) : `<section class="card"><h2>已提交结论</h2><dl class="detail"><div><dt>联系结果</dt><dd>${esc(contactLabels[data.contact_result] || '待确认')}</dd></div><div><dt>事实结论</dt><dd>${esc(TASK_KIND[kind].conclusions[data.conclusion] || '待确认')}</dd></div></dl><p class="muted">结论已经提交运营人员处置，不能由电销人员直接改变客资状态。</p></section>`;
  zsSetSafeHtml(app, shell(`<button class="btn small outline" data-history-back>返回</button><section class="detail-hero"><div><p class="eyebrow">${esc(TASK_KIND[kind].label)}</p><h1>${esc(lead.customer_name || '待核验客户')}</h1><span class="badge ${statusClass(data.status)}">${esc(statusLabel(data.status))}</span></div>${data.status === 'IN_PROGRESS' ? `<button id="dial" class="btn gold">${icon('phone')}<span>一键拨号</span></button>` : ''}</section>${data.status === 'IN_PROGRESS' ? '<section class="quick-guide"><b>核验说明</b><span>拨号由您主动确认，只提交事实结论，不决定派发、退款或终审。</span><a href="#result-form">填写结果</a></section>' : ''}<section class="card compact"><dl class="detail"><div><dt>手机号</dt><dd><strong>${esc(lead.phone || lead.phone_masked || '--')}</strong></dd></div><div><dt>地区</dt><dd>${esc(lead.city || '--')} ${esc(lead.district || '')}</dd></div>${details}</dl></section>${action}`, data.status === 'SUBMITTED' ? 'records' : 'verify', '核验详情'));
  bind();
  bindTaskActions(kind, id);
}

function bindTaskActions(kind, id) {
  document.querySelector('#start')?.addEventListener('click', async () => { try { await api(taskPath(kind, id, 'start'), { method: 'POST' }); toast('已开始核验'); task(kind, id); } catch (error) { toast(error.message, 'error'); } });
  document.querySelector('#dial')?.addEventListener('click', async () => { try { const result = await api(taskPath(kind, id, 'dial'), { method: 'POST' }); location.href = result.tel_url; } catch (error) { toast(error.message, 'error'); } });
  document.querySelector('#submit')?.addEventListener('click', () => submit(kind, id));
}

async function submit(kind, id) {
  const note = document.querySelector('#note').value.trim();
  if (note.length < 2) { toast('请填写至少 2 个字的核验备注', 'error'); return; }
  try {
    await api(taskPath(kind, id, 'submit'), { method: 'POST', body: JSON.stringify({ contact_result: document.querySelector('#contact_result').value, conclusion: document.querySelector('input[name=conclusion]:checked').value, note }) });
    toast('事实核验已提交运营处置');
    task(kind, id);
  } catch (error) { toast(error.message, 'error'); }
}

async function profile() {
  if (!await auth()) return;
  zsSetSafeHtml(app, shell(`<h1>我的工作台</h1><section class="card"><div class="brand"><img src="./logo.png" alt="合家美宅"><div>${esc(me.display_name)}<small>电销人员</small></div></div><dl class="detail"><div><dt>工作范围</dt><dd>仅查看和处理运营派发给您的任务；不具备自主领取、转派、派发、终审、退款或积分操作权限。</dd></div></dl></section><section class="card"><button id="logout" class="btn danger block">退出登录</button></section>`, 'profile', '个人中心'));
  bind();
  document.querySelector('#logout').onclick = async () => { await api('/auth/logout', { method: 'POST' }).catch(() => {}); me = null; location.hash = '#/home'; await route(); };
}

async function route() {
  const parts = (location.hash.replace(/^#\/?/, '') || 'home').split('?')[0].split('/');
  try {
    if (parts[0] === 'home') return await home();
    if (parts[0] === 'verify') return await verify();
    if (parts[0] === 'records') return await records();
    if (parts[0] === 'task' && parts[1] && parts[2]) return await task(parts[1], parts[2]);
    if (parts[0] === 'profile') return await profile();
    return await home();
  } catch (error) { toast(error.message || '加载失败', 'error'); }
}

window.addEventListener('hashchange', route);
route();
