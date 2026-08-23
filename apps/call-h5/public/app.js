const API = '/api/v1';
const app = document.querySelector('#app');
const toastEl = document.querySelector('#toast');

let me = null;

const ROLE_HOME_CONTRACT = { TELESALES: '电话核验' };
const ROLE_HOME_PRIORITY = ['TELESALES', 'FRANCHISE_OWNER'];
const TELESALES_HOME_CONTRACT = {
  metrics: ['待开始', '核验中', '已提交'],
  primaryActions: ['开始核验', '继续核验'],
  detail: ['一键拨号', '核验说明', '填写结果'],
};

const reasonLabels = {
  EMPTY_NUMBER: '空号或停机',
  OUT_OF_SERVICE_REGION: '超出服务区域',
  DUPLICATE_TO_RECEIVER: '接收方重复客资',
  NON_HOUSING_CONSULTATION: '非建房装修咨询',
};
const statusLabels = {
  PENDING: '待领取',
  ASSIGNED: '待处理',
  IN_PROGRESS: '核验中',
  SUBMITTED: '已提交',
};
const contactLabels = {
  CONNECTED: '已接通',
  NO_ANSWER: '无人接听',
  EMPTY_NUMBER: '空号',
  OUT_OF_SERVICE: '停机',
  WRONG_PERSON: '非本人',
  REFUSED: '拒接/拒访',
  OTHER: '其他',
};
const conclusionLabels = {
  SUPPORT_RETURN: '支持退回',
  DOES_NOT_SUPPORT_RETURN: '不支持退回',
  INCONCLUSIVE: '信息不足',
};
const ROLE_LABEL = {
  TELESALES: '电销核验',
  SUPER_ADMIN: '平台管理员',
};
const TECHNICAL_CODE = /^(?:[A-Z][A-Z0-9_]{2,}|[a-z][a-z0-9]*|[a-z0-9]+(?:[_-][a-z0-9]+)+)$/;
const readableLabel = (mapping, value, fallback = '待确认') => {
  const text = String(value ?? '').trim();
  if (!text) return fallback;
  return mapping[text] || (TECHNICAL_CODE.test(text) ? fallback : text);
};
const statusLabel = (value) => readableLabel(statusLabels, value, '待确认');
const reasonLabel = (value) => readableLabel(reasonLabels, value, '其他原因');
const roleLabel = (value) => readableLabel(ROLE_LABEL, value, '内部账号');

const esc = (value = '') =>
  String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  }[char]));
const fmt = (value) =>
  value
    ? new Date(value).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
    : '--';
const icon = (name) => window.ZSIconSystem?.svg?.(name) || '';
const evidenceCount = (request) =>
  Object.values(request.evidence_summary || {}).reduce((sum, count) => sum + Number(count || 0), 0);
const statusClass = (status) =>
  status === 'SUBMITTED' ? 'done' : status === 'IN_PROGRESS' ? 'doing' : 'pending';

function toast(message, type = '') {
  toastEl.textContent = message;
  toastEl.className = `toast show ${type}`;
  setTimeout(() => {
    toastEl.className = 'toast';
  }, 2400);
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(API + path, { ...opts, headers, credentials: 'include' });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.code !== 'OK') {
    const error = new Error(payload.message || '请求失败');
    error.code = payload.code;
    throw error;
  }
  return payload.data;
}

function nav(active) {
  return `<nav class="bottom" aria-label="底部导航">${
    [
      ['home', 'home', '首页'],
      ['tasks', 'phone', '核验'],
      ['profile', 'user', '我的'],
    ].map(([route, iconName, label]) => (
      `<button class="nav ${active === route ? 'active' : ''}" data-route="${route}">
        <i>${icon(iconName)}</i><span>${label}</span>
      </button>`
    )).join('')
  }</nav>`;
}

function shell(content, active = 'home', title = '电销核验台') {
  return `<div class="shell">
    <header class="top">
      <div class="brand">
        <img src="./logo.png" alt="合家美宅">
        <div>合家美宅<small>${esc(title)} · 退回申诉电话核验</small></div>
      </div>
      <button class="btn small outline icon-btn" id="refresh">${icon('rotate-ccw')}<span>刷新</span></button>
    </header>
    <main class="content">${content}</main>
    ${nav(active)}
  </div>`;
}

function bind() {
  document.querySelectorAll('[data-route]').forEach((node) => {
    node.onclick = () => go(node.dataset.route);
  });
  document.querySelectorAll('[data-history-back]').forEach((node) => {
    node.onclick = () => (history.length > 1 ? history.back() : go('tasks'));
  });
  const refresh = document.querySelector('#refresh');
  if (refresh) refresh.onclick = route;
}

function go(routeName) {
  const next = '#/' + routeName;
  if (location.hash === next) route();
  else location.hash = next;
}

async function auth() {
  try {
    me = await api('/auth/me');
    if (!me.roles.includes('TELESALES') && !me.roles.includes('SUPER_ADMIN')) {
      throw new Error('当前账号不是电销岗位');
    }
    return true;
  } catch (error) {
    renderLogin(error.code ? '' : error.message);
    return false;
  }
}

function renderLogin(message = '') {
  zsSetSafeHtml(app, `<section class="login">
    <div class="login-brand">
      <span class="login-kicker">合家美宅 · 内部登录</span>
      <img src="./logo.png" alt="合家美宅">
      <h1>电销核验工作台</h1>
      <p>统一账号登录后，系统会按权限自动进入对应岗位页面，待办和核验结果都能一眼看清。</p>
    </div>
    <div class="panel login-card">
      <div class="login-card-head">
        <span>内部账号登录</span>
        <h2>欢迎回来</h2>
        <p>请使用平台分配的账号和密码登录，系统会自动进入对应页面。</p>
      </div>
      ${message ? `<p class="error-text">${esc(message)}</p>` : ''}
      <form id="call-login-form" novalidate>
        <div class="login-field">
          <label for="user">登录账号</label>
          <div class="login-input-wrap"><i aria-hidden="true">${icon('user')}</i><input id="user" name="username" autocomplete="username" placeholder="请输入电销账号" required></div>
        </div>
        <div class="login-field">
          <label for="pass">登录密码</label>
          <div class="login-input-wrap"><i aria-hidden="true">${icon('lock')}</i><input id="pass" name="password" type="password" autocomplete="current-password" placeholder="请输入登录密码" required></div>
        </div>
        <button id="login" class="btn primary block login-submit" type="submit">登录工作台</button>
      </form>
      <p class="login-security">完整客户电话仅在领取任务后显示，请妥善保管账号。</p>
    </div>
  </section>`);

  document.querySelector('#call-login-form').onsubmit = async (event) => {
    event.preventDefault();
    const button = document.querySelector('#login');
    button.disabled = true;
    button.textContent = '正在登录…';
    try {
      await api('/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          username: document.querySelector('#user').value.trim(),
          password: document.querySelector('#pass').value,
        }),
      });
      location.replace('/admin/');
    } catch (error) {
      button.disabled = false;
      button.textContent = '登录工作台';
      toast(error.message, 'error');
    }
  };
}

function metric(items, statuses) {
  return items.filter((item) => statuses.includes(item.status)).length;
}

function taskCard(task) {
  const lead = task.lead || {};
  const request = task.return_request || {};
  return `<article class="task" data-task="${task.id}" tabindex="0">
    <div class="row">
      <h3>${esc(lead.customer_name || '待核验客户')}</h3>
      <span class="badge ${statusClass(task.status)}">${esc(statusLabel(task.status))}</span>
    </div>
    <p class="task-meta">${esc(lead.city || '')} ${esc(lead.district || '')}</p>
    <dl class="task-facts">
      <div><dt>退回原因</dt><dd>${esc(reasonLabel(request.reason_code))}</dd></div>
      <div><dt>证据</dt><dd>${evidenceCount(request)} 份</dd></div>
      <div><dt>期限</dt><dd>${fmt(request.appeal_deadline_at || task.due_at)}</dd></div>
    </dl>
    <p>${esc(request.description || '暂无申诉说明')}</p>
  </article>`;
}

async function home() {
  if (!await auth()) return;
  const tasks = await api('/v1.2/return-verifications/tasks?mine=true&page=1&page_size=200');
  const actionableTasks = tasks.items.filter((item) => item.status !== 'SUBMITTED');
  const hasDoing = actionableTasks.some((item) => item.status === 'IN_PROGRESS');

  zsSetSafeHtml(app, shell(`
    <section class="home-title">
      <p class="eyebrow">个人核验工作台</p>
      <h1>您好，${esc(me.display_name)}</h1>
      <p class="muted">按退回申诉优先级回访客户，核实号码与咨询事实。</p>
    </section>
    <section class="hero">
      <div>
        <small>当前待办</small>
        <strong>${actionableTasks.length}</strong>
        <span>待开始和核验中的任务</span>
      </div>
      <button class="btn gold" data-route="tasks">${icon(hasDoing ? 'user-check' : 'phone')}<span>${hasDoing ? '继续核验' : '开始核验'}</span></button>
    </section>
    <section class="metrics" aria-label="个人任务统计">
      <button type="button" class="metric" data-route="tasks?status=TODO" aria-label="待开始 ${metric(tasks.items, ['PENDING', 'ASSIGNED'])} 条，查看任务"><span>待开始</span><b>${metric(tasks.items, ['PENDING', 'ASSIGNED'])}</b></button>
      <button type="button" class="metric" data-route="tasks?status=IN_PROGRESS" aria-label="核验中 ${metric(tasks.items, ['IN_PROGRESS'])} 条，查看任务"><span>核验中</span><b>${metric(tasks.items, ['IN_PROGRESS'])}</b></button>
      <button type="button" class="metric" data-route="tasks?status=SUBMITTED" aria-label="已提交 ${metric(tasks.items, ['SUBMITTED'])} 条，查看任务"><span>已提交</span><b>${metric(tasks.items, ['SUBMITTED'])}</b></button>
    </section>
    <section class="card">
      <div class="row section-head">
        <h2>优先任务</h2>
        <button class="btn small outline" data-route="tasks">全部</button>
      </div>
      ${actionableTasks.length ? actionableTasks.slice(0, 5).map(taskCard).join('') : emptyState('暂无待办任务', '新的退回申诉核验任务会出现在这里。')}
    </section>
  `, 'home'));
  bind();
  bindTaskCards();
}

async function tasks() {
  if (!await auth()) return;
  const query = new URLSearchParams(location.hash.split('?')[1] || '');
  const status = query.get('status') || '';
  const apiStatus = status === 'TODO' ? '' : status;
  const data = await api(`/v1.2/return-verifications/tasks?mine=true&page=1&page_size=100${apiStatus ? `&status=${encodeURIComponent(apiStatus)}` : ''}`);
  const visibleItems = status === 'TODO'
    ? data.items.filter((item) => ['PENDING', 'ASSIGNED'].includes(item.status))
    : data.items;

  zsSetSafeHtml(app, shell(`
    <h1>核验任务</h1>
    <div class="filters" role="tablist">
      ${[
        ['', '全部'],
        ['TODO', '待开始'],
        ['IN_PROGRESS', '核验中'],
        ['SUBMITTED', '已提交'],
      ].map(([value, label]) => (
        `<button class="btn small ${status === value ? 'primary' : 'outline'}" data-filter="${value}">${label}</button>`
      )).join('')}
    </div>
    ${visibleItems.length ? visibleItems.map(taskCard).join('') : emptyState('暂无符合条件的任务', '切换筛选或稍后刷新。')}
  `, 'tasks', '核验任务'));
  bind();
  bindTaskCards();
  document.querySelectorAll('[data-filter]').forEach((node) => {
    node.onclick = () => {
      location.hash = `#/tasks${node.dataset.filter ? `?status=${node.dataset.filter}` : ''}`;
    };
  });
}

function bindTaskCards() {
  document.querySelectorAll('[data-task]').forEach((node) => {
    const open = () => go('task/' + node.dataset.task);
    node.onclick = open;
    node.onkeydown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        open();
      }
    };
  });
}

async function task(id) {
  if (!await auth()) return;
  const data = await api(`/v1.2/return-verifications/tasks/${id}`);
  const lead = data.lead || {};
  const request = data.return_request || {};
  const submitted = data.status === 'SUBMITTED' ? submittedResult(data) : '';
  const activeWork = data.status === 'IN_PROGRESS' ? form() : '';
  const pendingWork = ['PENDING', 'ASSIGNED'].includes(data.status) ? claimBox() : '';

  zsSetSafeHtml(app, shell(`
    <button class="btn small outline" data-history-back>返回</button>
    <section class="detail-hero">
      <div>
        <p class="eyebrow">核验详情</p>
        <h1>${esc(lead.customer_name || '待核验客户')}</h1>
        <span class="badge ${statusClass(data.status)}">${esc(statusLabel(data.status))}</span>
      </div>
      ${data.status === 'IN_PROGRESS' ? `<button id="dial" class="btn gold">${icon('phone')}<span>一键拨号</span></button>` : ''}
    </section>
    ${data.status === 'IN_PROGRESS' ? `<section class="quick-guide">
      <b>核验说明</b>
      <span>拨号后回到本页填写结果，只记录事实结论。</span>
      <a href="#result-form">填写结果</a>
    </section>` : ''}
    <section class="card compact">
      <dl class="detail">
        <div><dt>手机号</dt><dd><strong>${esc(lead.phone || lead.phone_masked || '--')}</strong></dd></div>
        <div><dt>地区</dt><dd>${esc(lead.city || '--')} ${esc(lead.district || '')}</dd></div>
        <div><dt>退回原因</dt><dd>${esc(reasonLabel(request.reason_code))}</dd></div>
        <div><dt>证据数量</dt><dd>${evidenceCount(request)} 份</dd></div>
        <div><dt>处理期限</dt><dd>${fmt(request.appeal_deadline_at || data.due_at)}</dd></div>
        <div><dt>申诉说明</dt><dd>${esc(request.description || '--')}</dd></div>
      </dl>
    </section>
    ${pendingWork || activeWork || submitted}
  `, 'tasks', '核验详情'));
  bind();
  bindTaskActions(id);
}

function claimBox() {
  return `<section class="card">
    <h2>核验说明</h2>
    <p class="muted">领取后可查看完整手机号；任务会记录在您的个人待办中。</p>
    <button class="btn primary block" id="claim">开始核验</button>
  </section>`;
}

function form() {
  return `<section class="card" id="result-form">
    <h2>填写结果</h2>
    <div class="form">
      <label>联系结果 *</label>
      <select id="contact_result" class="select">
        ${Object.entries(contactLabels).map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}
      </select>
    </div>
    <div class="form">
      <label>核验结论 *</label>
      <div class="radio-grid">
        ${Object.entries(conclusionLabels).map(([value, label]) => (
          `<label class="choice"><input type="radio" name="conclusion" value="${value}" ${value === 'INCONCLUSIVE' ? 'checked' : ''}> ${label}</label>`
        )).join('')}
      </div>
    </div>
    <div class="form">
      <label>核验备注 *</label>
      <textarea id="note" class="textarea" placeholder="至少 2 个字，记录客户的说法和您的判断"></textarea>
    </div>
    <button id="submit" class="btn primary block">提交核验结果</button>
  </section>`;
}

function submittedResult(data) {
  return `<section class="card">
    <h2>已提交结论</h2>
    <dl class="detail">
      <div><dt>联系结果</dt><dd>${esc(readableLabel(contactLabels, data.contact_result, '待确认'))}</dd></div>
      <div><dt>核验结论</dt><dd>${esc(readableLabel(conclusionLabels, data.conclusion, '待确认'))}</dd></div>
    </dl>
    <div class="action-row">
      <button class="btn primary" data-route="tasks">继续下一条</button>
      <button class="btn outline" data-route="tasks">返回任务列表</button>
    </div>
  </section>`;
}

function bindTaskActions(id) {
  const claim = document.querySelector('#claim');
  if (claim) {
    claim.onclick = async () => {
      try {
        await api(`/v1.2/return-verifications/tasks/${id}/claim`, { method: 'POST' });
        toast('任务已领取');
        task(id);
      } catch (error) {
        toast(error.message, 'error');
      }
    };
  }

  const dial = document.querySelector('#dial');
  if (dial) {
    dial.onclick = async () => {
      try {
        const result = await api(`/v1.2/return-verifications/tasks/${id}/dial`, { method: 'POST' });
        location.href = result.tel_url;
      } catch (error) {
        toast(error.message, 'error');
      }
    };
  }

  const submitButton = document.querySelector('#submit');
  if (submitButton) submitButton.onclick = () => submit(id);
}

async function submit(id) {
  const contactResult = document.querySelector('#contact_result').value;
  const conclusion = document.querySelector('input[name=conclusion]:checked').value;
  const note = document.querySelector('#note').value.trim();
  if (note.length < 2) {
    toast('请填写至少 2 个字的核验备注', 'error');
    return;
  }
  try {
    await api(`/v1.2/return-verifications/tasks/${id}/submit`, {
      method: 'POST',
      body: JSON.stringify({ contact_result: contactResult, conclusion, note }),
    });
    toast('事实核验已提交');
    task(id);
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function profile() {
  if (!await auth()) return;
  const roles = me.roles.map(roleLabel).join('、');
  zsSetSafeHtml(app, shell(`
    <h1>我的工作台</h1>
    <section class="card">
      <div class="brand">
        <img src="./logo.png" alt="合家美宅">
        <div>${esc(me.display_name)}<small>内部电销账号</small></div>
      </div>
      <dl class="detail">
        <div><dt>岗位</dt><dd>${esc(roles)}</dd></div>
        <div><dt>工作范围</dt><dd>可查看和处理分配给您的电话核验任务；不展示客资核验外的管理信息。</dd></div>
      </dl>
    </section>
    <section class="card">
      <button id="logout" class="btn danger block">退出登录</button>
    </section>
  `, 'profile', '个人中心'));
  bind();
  document.querySelector('#logout').onclick = async () => {
    await api('/auth/logout', { method: 'POST' }).catch(() => {});
    me = null;
    location.replace('/admin/index.html');
  };
}

function emptyState(title, desc) {
  return `<div class="empty">
    <b>${esc(title)}</b>
    <span>${esc(desc)}</span>
  </div>`;
}

async function route() {
  const raw = location.hash.replace(/^#\/?/, '') || 'home';
  const parts = raw.split('?')[0].split('/');
  try {
    if (parts[0] === 'home') return await home();
    if (parts[0] === 'tasks') return await tasks();
    if (parts[0] === 'task' && parts[1]) return await task(parts[1]);
    if (parts[0] === 'profile') return await profile();
    return await home();
  } catch (error) {
    console.error(error);
    toast(error.message || '加载失败', 'error');
  }
}

window.addEventListener('hashchange', route);
route();
