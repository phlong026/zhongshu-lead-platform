const API = '/api/v1';
const app = document.querySelector('#app');
const toastEl = document.querySelector('#toast');
const overlay = document.querySelector('#overlay');
const supplierIcon = (name, className = 'zs-svg-icon') =>
  window.ZSIconSystem?.svg(name, className) || '';

const state = {
  me: null,
  tab: 'list',
  capabilities: [],
  items: [],
  cities: [],
  districts: [],
  sourceOptions: [],
  categoryOptions: [],
  leadOptionsLoaded: false,
  editing: null,
  listPage: 1,
  listPageSize: 20,
  listStatus: '',
  listTotal: 0,
};

const labels = {
  DRAFT: '待完善',
  PENDING_REVIEW: '平台审核中',
  READY_DISPATCH: '已进入派发',
  DUPLICATE: '重复信息复核中',
  INVALID: '需要修改',
  CLOSED: '已关闭',
  PENDING: '审核中',
  APPROVED: '审核通过',
  REJECTED: '需要修改',
  CLEAR: '未发现重复',
  HARD_DUPLICATE: '近期已有相同客户',
  REWARD_DUPLICATE: '已有相同客户记录',
  HISTORICAL_SUSPECT: '历史记录待确认',
  OVERRIDDEN: '已人工确认',
  PENDING_CLAIM: '待领取',
  CLAIMED: '已领取',
  FOLLOWING: '跟进中',
  RETURN_PENDING: '退回处理中',
  RETURNED: '已退回',
  RELEASED: '已释放',
  EXPIRED: '已过期',
  COMPLETED: '已完成',
  OLD_RENOVATION: '旧房改造',
  SELF_BUILD: '农村自建房',
  INTERIOR: '室内装修',
  MANUAL: '人工录入',
  DOUYIN: '抖音/信息流',
  WECHAT_VIDEO: '视频号',
  XIAOHONGSHU: '小红书',
  '供应商推荐': '加盟商推荐',
};
const TECHNICAL_CODE = /^(?:[A-Z][A-Z0-9_]{2,}|[a-z][a-z0-9]*|[a-z0-9]+(?:[_-][a-z0-9]+)+)$/;
const readableLabel = (value, fallback = '待确认') => {
  const text = String(value ?? '').trim();
  if (!text) return fallback;
  return labels[text] || (TECHNICAL_CODE.test(text) ? fallback : text);
};
const DEFAULT_SOURCE_OPTIONS = [
  { code: '供应商推荐', label: '加盟商推荐' },
  { code: 'DOUYIN', label: '抖音/信息流' },
  { code: 'WECHAT_VIDEO', label: '视频号' },
  { code: 'XIAOHONGSHU', label: '小红书' },
  { code: 'MANUAL', label: '人工录入' },
];
const DEFAULT_CATEGORY_OPTIONS = [
  { code: 'OLD_RENOVATION', label: '旧房改造' },
  { code: 'SELF_BUILD', label: '农村自建房' },
  { code: 'INTERIOR', label: '室内装修' },
];

function selectOptions(items, current, emptyLabel, legacyLabel) {
  const options = new Map();
  items.forEach((item) => {
    if (item?.code && !options.has(item.code)) {
      options.set(item.code, {
        code: item.code,
        label: item.label || readableLabel(item.code, legacyLabel),
      });
    }
  });
  if (current && !options.has(current)) {
    options.set(current, {
      code: current,
      label: readableLabel(current, legacyLabel),
    });
  }
  return (
    `<option value="">${esc(emptyLabel)}</option>` +
    [...options.values()]
      .map(
        (item) =>
          `<option value="${esc(item.code)}" ${item.code === current ? 'selected' : ''}>${esc(item.label)}</option>`,
      )
      .join('')
  );
}

const fieldControls = {
  customer_name: '#lead-name',
  phone: '#lead-phone',
  city: '#lead-city',
  region_code: '#lead-city',
  source_channel: '#lead-source',
  category_code: '#lead-category',
  budget_min: '#lead-budget-min',
  budget_max: '#lead-budget-max',
  need_summary: '#lead-need',
  consent_confirmed: '#lead-consent',
};

const esc = (input = '') =>
  String(input ?? '').replace(
    /[&<>'"]/g,
    (char) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;',
      })[char],
  );

function fmt(input) {
  if (!input) return '--';
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function value(selector) {
  return document.querySelector(selector)?.value?.trim() || '';
}

function statusClass(status) {
  return (
    {
      READY_DISPATCH: 'ok',
      APPROVED: 'ok',
      CLEAR: 'ok',
      OVERRIDDEN: 'blue',
      PENDING_REVIEW: 'warn',
      PENDING: 'warn',
      DUPLICATE: 'warn',
      REWARD_DUPLICATE: 'warn',
      HISTORICAL_SUSPECT: 'warn',
      HARD_DUPLICATE: 'bad',
      INVALID: 'bad',
      REJECTED: 'bad',
    }[status] || ''
  );
}

function badge(status) {
  return `<span class="supplier-status ${statusClass(status)}">${esc(
    readableLabel(status),
  )}</span>`;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(API + path, {
    ...options,
    headers,
    credentials: 'include',
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = { message: response.statusText };
  }
  if (!response.ok || payload.code !== 'OK') {
    const error = new Error(payload.message || '请求失败，请稍后重试');
    error.code = payload.code;
    error.details = payload.details;
    throw error;
  }
  return payload.data;
}

function toast(message, type = '') {
  toastEl.textContent = message;
  toastEl.className = `toast show ${type === 'error' ? 'error' : ''}`;
  window.setTimeout(() => {
    toastEl.className = 'toast';
  }, 2600);
}

function capability() {
  return state.capabilities.find(
    (item) => item.capability_code === 'LEAD_SUPPLIER',
  );
}

function capabilityApproved() {
  const item = capability();
  return Boolean(item?.active && item?.review_status === 'APPROVED');
}

function capabilityBlock() {
  const item = capability();
  if (capabilityApproved()) {
    return `
      <div class="supplier-capability-copy">
        <b>现在可以上传客资</b>
        <span>平台审核结果会在“我的客资”中更新</span>
      </div>
      <button class="supplier-btn gold small" id="hero-upload">上传新客资</button>
    `;
  }
  if (item?.review_status === 'PENDING') {
    return `
      <div class="supplier-capability-copy">
        <b>开通申请审核中</b>
        <span>审核完成后即可上传，无需重复申请</span>
      </div>
      ${badge('PENDING')}
    `;
  }
  if (item?.review_status === 'REJECTED') {
    return `
      <div class="supplier-capability-copy">
        <b>开通申请需要补充</b>
        <span>${esc(item.review_note || '请根据平台说明重新提交申请')}</span>
      </div>
      <button class="supplier-btn gold small" id="request-capability">重新申请</button>
    `;
  }
  return `
    <div class="supplier-capability-copy">
      <b>先申请开通客资供应</b>
      <span>平台确认加盟商资质后即可上传</span>
    </div>
    <button class="supplier-btn gold small" id="request-capability">申请开通</button>
  `;
}

function header() {
  return `
    <header class="supplier-header">
      <div class="supplier-brand">
        <img src="./logo.png" alt="合家美宅">
        <div>
          <strong>合家美宅</strong>
          <small>${esc(state.me?.display_name || '加盟商')} · 加盟商供客</small>
        </div>
      </div>
      <button class="supplier-back" id="back-h5">返回工作台</button>
    </header>
  `;
}

function hero() {
  return `
    <section class="supplier-hero">
      <div class="supplier-hero-head">
        <div>
          <h1>客资上传</h1>
          <p>确认客户授权后提交资料，并在这里查看审核和派发进度。</p>
        </div>
        <a class="supplier-reward-link" href="./v12-workbench.html?view=rewards">奖励进度</a>
      </div>
      <div class="supplier-capability">${capabilityBlock()}</div>
    </section>
  `;
}

function shell(content, { showHero = state.tab === 'list' } = {}) {
  zsSetSafeHtml(
    app,
    `${header()}
      <main class="supplier-main">
        ${showHero ? hero() : ''}
        <nav class="supplier-tabs" aria-label="加盟商客资操作">
          <button class="supplier-tab ${state.tab === 'list' ? 'active' : ''}" data-tab="list">
            我的客资
          </button>
          <button
            class="supplier-tab ${state.tab === 'upload' ? 'active' : ''}"
            data-tab="upload"
            ${capabilityApproved() ? '' : 'disabled'}
          >
            上传客资
          </button>
        </nav>
        ${content}
      </main>`,
  );
  bindCommon();
}

function bindCommon() {
  const backButton = document.querySelector('#back-h5');
  if (backButton) backButton.onclick = () => {
    location.href = './v12-workbench.html?view=profile';
  };
  document.querySelectorAll('[data-tab]').forEach((button) => {
    button.onclick = () => {
      if (button.disabled) return;
      state.tab = button.dataset.tab;
      state.editing = null;
      render();
    };
  });
  const requestButton = document.querySelector('#request-capability');
  if (requestButton) requestButton.onclick = () => requestSupplierCapability(requestButton);
  const uploadButton = document.querySelector('#hero-upload');
  if (uploadButton) uploadButton.onclick = startUpload;
}

function loading() {
  shell('<div class="supplier-card supplier-loading">正在加载…</div>', {
    showHero: false,
  });
}

function closeSheet() {
  zsSetSafeHtml(overlay, '');
}

function openSheet(title, body) {
  zsSetSafeHtml(
    overlay,
    `
      <div class="supplier-overlay">
        <section class="supplier-sheet" role="dialog" aria-modal="true" aria-labelledby="supplier-sheet-title">
          <div class="supplier-sheet-head">
            <h2 id="supplier-sheet-title">${esc(title)}</h2>
            <button class="supplier-btn small" id="close-sheet">关闭</button>
          </div>
          ${body}
        </section>
      </div>
    `,
  );
  document.querySelector('#close-sheet').onclick = closeSheet;
}

async function boot() {
  try {
    state.me = await api('/auth/me');
    const permissions = state.me.permissions || [];
    if (!permissions.includes('*') && !permissions.includes('supplier.lead.manage')) {
      throw new Error('当前账号没有加盟商客资权限');
    }
    state.capabilities = await api('/v1.2/company/capabilities');
    await render();
  } catch (error) {
    if (error.code === 'AUTH_REQUIRED' || error.code === 'AUTH_INVALID') {
      location.href = './#/login';
      return;
    }
    zsSetSafeHtml(
      app,
      `${header()}<main class="supplier-main"><div class="supplier-error">${esc(
        error.message || '页面加载失败',
      )}</div></main>`,
    );
    const backButton = document.querySelector('#back-h5');
    if (backButton) backButton.onclick = () => {
      location.href = './v12-workbench.html?view=profile';
    };
  }
}

async function render() {
  loading();
  try {
    if (state.tab === 'upload') {
      await renderUpload(state.editing);
    } else {
      await renderList();
    }
  } catch (error) {
    toast(error.message, 'error');
    shell(
      `<div class="supplier-error">${esc(error.message || '加载失败')}</div>`,
      { showHero: false },
    );
  }
}

async function requestSupplierCapability(button) {
  if (button?.dataset.busy === '1') return;
  if (button) {
    button.dataset.busy = '1';
    button.disabled = true;
  }
  try {
    await api('/v1.2/company/capabilities', {
      method: 'POST',
      body: JSON.stringify({ capability_code: 'LEAD_SUPPLIER' }),
    });
    state.capabilities = await api('/v1.2/company/capabilities');
    toast('开通申请已提交');
    await render();
  } catch (error) {
    if (button) {
      delete button.dataset.busy;
      button.disabled = false;
    }
    toast(error.message, 'error');
  }
}

function startUpload() {
  state.tab = 'upload';
  state.editing = null;
  renderUpload();
}

function queryString(values) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, item]) => {
    if (item !== undefined && item !== null && item !== '') {
      params.set(key, item);
    }
  });
  const result = params.toString();
  return result ? `?${result}` : '';
}

function leadProgress(item) {
  if (item.status === 'DRAFT') {
    return '资料尚未提交，可以继续补充或删除草稿。';
  }
  if (item.status === 'PENDING_REVIEW') {
    return '平台正在审核资料，结果会在这里更新。';
  }
  if (item.status === 'DUPLICATE') {
    return '平台正在核对重复信息，暂时无需再次提交。';
  }
  if (item.status === 'INVALID') {
    return item.review_note || '请按平台说明修改后重新提交。';
  }
  if (item.status === 'READY_DISPATCH') {
    return '资料已通过审核，正在等待人工派发。';
  }
  return '';
}

function leadActions(item) {
  if (item.status === 'DRAFT') {
    return `
      <button class="supplier-btn small primary" data-edit="${item.id}">继续填写并提交</button>
      <button class="supplier-btn small danger" data-delete="${item.id}">删除草稿</button>
    `;
  }
  if (item.status === 'INVALID' && item.review_status === 'REJECTED') {
    return `
      <button class="supplier-btn small primary" data-revise="${item.id}">修改后重新提交</button>
      <button class="supplier-btn small" data-detail="${item.id}">查看说明</button>
    `;
  }
  const text = ['PENDING_REVIEW', 'DUPLICATE'].includes(item.status)
    ? '查看进度'
    : '查看详情';
  return `<button class="supplier-btn small primary" data-detail="${item.id}">${text}</button>`;
}

function emptyList() {
  const initialEmpty = state.listTotal === 0 && !state.listStatus;
  const title = initialEmpty ? '还没有客资记录' : '当前筛选下没有客资';
  const copy = initialEmpty
    ? '上传后可在这里查看草稿、审核和派发进度。'
    : '可以切换状态查看其他客资。';
  const action =
    initialEmpty && capabilityApproved()
      ? '<button class="supplier-btn primary" id="empty-upload">上传第一条客资</button>'
      : !initialEmpty
        ? '<button class="supplier-btn" id="clear-status-filter">查看全部客资</button>'
        : '';
  return `
    <div class="supplier-empty">
      <div class="supplier-empty-icon">${supplierIcon('inbox')}</div>
      <h3>${title}</h3>
      <p>${copy}</p>
      ${action}
    </div>
  `;
}

async function renderList() {
  const data = await api(
    '/v1.2/supplier/leads' +
      queryString({
        page: state.listPage,
        page_size: state.listPageSize,
        status: state.listStatus,
      }),
  );
  state.items = data.items || [];
  state.listTotal = data.total || 0;
  const totalPages = Math.max(1, Math.ceil(state.listTotal / state.listPageSize));
  if (state.listPage > totalPages) {
    state.listPage = totalPages;
    return renderList();
  }

  const rows = state.items.map((item) => {
    const timeLabel = item.status === 'DRAFT' ? '最后更新' : '提交时间';
    const timeValue = item.status === 'DRAFT' ? item.updated_at : item.submitted_at;
    const progress = leadProgress(item);
    return `
      <article class="supplier-lead">
        <div class="supplier-lead-top">
          <div>
            <h3>${esc(item.customer_name === '未填写' ? '未填写姓名' : item.customer_name || '未填写姓名')}</h3>
            <p>${esc(item.phone_masked || '手机号待补充')} · ${esc(
              item.city || '地区待补充',
            )} ${esc(item.district || '')}</p>
          </div>
          ${badge(item.status)}
        </div>
        ${progress ? `<div class="supplier-lead-progress">${esc(progress)}</div>` : ''}
        <div class="supplier-lead-meta">
          <span>${timeLabel}：${fmt(timeValue)}</span>
          ${item.duplicate_status ? `<span>重复情况：${esc(labels[item.duplicate_status] || '平台复核中')}</span>` : ''}
        </div>
        <div class="supplier-lead-actions">${leadActions(item)}</div>
      </article>
    `;
  });

  const showFilter = state.listTotal > 0 || Boolean(state.listStatus);
  const filter = showFilter
    ? `
      <label class="supplier-filter">
        <span>按进度筛选</span>
        <select class="supplier-select" id="supplier-status">
          <option value="" ${state.listStatus === '' ? 'selected' : ''}>全部进度</option>
          ${['DRAFT', 'PENDING_REVIEW', 'READY_DISPATCH', 'DUPLICATE', 'INVALID']
            .map(
              (option) =>
                `<option value="${option}" ${state.listStatus === option ? 'selected' : ''}>${esc(
                  labels[option],
                )}</option>`,
            )
            .join('')}
        </select>
      </label>
    `
    : '';
  const pager =
    totalPages > 1
      ? `
        <div class="supplier-pager">
          <button class="supplier-btn small" id="previous-page" ${state.listPage <= 1 ? 'disabled' : ''}>
            上一页
          </button>
          <span class="supplier-muted">第 ${state.listPage} / ${totalPages} 页，共 ${state.listTotal} 条</span>
          <button class="supplier-btn small" id="next-page" ${state.listPage >= totalPages ? 'disabled' : ''}>
            下一页
          </button>
        </div>
      `
      : '';

  shell(`
    <section class="supplier-card">
      <div class="supplier-card-head">
        <div>
          <h2>客资进度</h2>
        </div>
        ${filter}
      </div>
      <div class="supplier-list">${rows.length ? rows.join('') : emptyList()}</div>
      ${pager}
    </section>
  `);

  const statusFilter = document.querySelector('#supplier-status');
  if (statusFilter) {
    statusFilter.onchange = (event) => {
      state.listStatus = event.target.value;
      state.listPage = 1;
      renderList();
    };
  }
  const previous = document.querySelector('#previous-page');
  if (previous) {
    previous.onclick = () => {
      if (state.listPage > 1) {
        state.listPage -= 1;
        renderList();
      }
    };
  }
  const next = document.querySelector('#next-page');
  if (next) {
    next.onclick = () => {
      if (state.listPage < totalPages) {
        state.listPage += 1;
        renderList();
      }
    };
  }
  document.querySelectorAll('[data-detail]').forEach((button) => {
    button.onclick = () => showDetail(button.dataset.detail);
  });
  document.querySelectorAll('[data-edit]').forEach((button) => {
    button.onclick = () => editLead(button.dataset.edit);
  });
  document.querySelectorAll('[data-delete]').forEach((button) => {
    button.onclick = () => deleteDraft(button.dataset.delete);
  });
  document.querySelectorAll('[data-revise]').forEach((button) => {
    button.onclick = () => reviseLead(button.dataset.revise);
  });
  const emptyUpload = document.querySelector('#empty-upload');
  if (emptyUpload) emptyUpload.onclick = startUpload;
  const clearFilter = document.querySelector('#clear-status-filter');
  if (clearFilter) {
    clearFilter.onclick = () => {
      state.listStatus = '';
      state.listPage = 1;
      renderList();
    };
  }
}

async function ensureCities() {
  if (!state.cities.length) {
    state.cities = await api('/master-data/regions?level=CITY');
  }
  return state.cities;
}

async function loadDistricts(cityCode) {
  state.districts = cityCode
    ? await api(
        '/master-data/regions' +
          queryString({ parent_code: cityCode, level: 'DISTRICT' }),
      )
    : [];
  return state.districts;
}

async function ensureLeadOptions() {
  if (state.leadOptionsLoaded) return;
  const load = async (domain, fallback) => {
    try {
      const items = await api(`/master-data/dictionaries/${domain}`);
      return items?.length ? items : fallback;
    } catch (error) {
      console.warn(`未能加载${domain}选项，已使用默认选项`, error);
      return fallback;
    }
  };
  [state.sourceOptions, state.categoryOptions] = await Promise.all([
    load('source_channel', DEFAULT_SOURCE_OPTIONS),
    load('lead_category', DEFAULT_CATEGORY_OPTIONS),
  ]);
  state.leadOptionsLoaded = true;
}

async function editLead(id) {
  try {
    state.editing = await api(`/v1.2/supplier/leads/${id}`);
    state.tab = 'upload';
    await renderUpload(state.editing);
  } catch (error) {
    toast(error.message, 'error');
  }
}

function requiredMark() {
  return '<span class="supplier-required" aria-hidden="true">*</span>';
}

function fieldError(name) {
  return `<span class="supplier-field-error" data-field-error="${name}"></span>`;
}

async function renderUpload(item = null) {
  if (!capabilityApproved()) {
    state.tab = 'list';
    await renderList();
    return;
  }
  await Promise.all([ensureCities(), ensureLeadOptions()]);
  const city =
    state.cities.find((row) => row.name === item?.city) ||
    state.cities.find((row) => row.code === item?.region_code) ||
    null;
  await loadDistricts(city?.code || '');
  const district =
    state.districts.find((row) => row.name === item?.district) ||
    state.districts.find((row) => row.code === item?.region_code) ||
    null;
  const rejectedNotice = item?.review_note
    ? `<div class="supplier-error supplier-review-note"><b>平台修改说明</b><span>${esc(
        item.review_note,
      )}</span></div>`
    : '';
  const phoneHelp = item
    ? '为保护客户隐私，请核对手机号；如输入框为空，重新编辑时请再次填写完整手机号。'
    : '手机号仅用于客资去重和业务联系，平台会加密保护。';

  shell(
    `
      <section class="supplier-card supplier-form-card">
        <div class="supplier-card-head">
          <div>
            <h2>${item ? '完善客资资料' : '上传新客资'}</h2>
            <div class="supplier-muted">可以先保存，确认完整后再提交平台审核</div>
          </div>
          <button class="supplier-btn small" id="return-to-list">返回列表</button>
        </div>
        ${rejectedNotice}
        <form class="supplier-form" id="lead-form" novalidate>
          <div id="form-error-summary" class="supplier-form-error" role="alert" tabindex="-1" hidden></div>

          <section class="supplier-form-section" aria-labelledby="customer-section-title">
            <div class="supplier-form-section-head">
              <span class="supplier-step">1</span>
              <div>
                <h3 id="customer-section-title">客户信息</h3>
                <p>用于识别客户并核对是否重复</p>
              </div>
            </div>
            <div class="supplier-grid">
              <div class="supplier-field">
                <label for="lead-name">客户姓名 ${requiredMark()}</label>
                <input
                  class="supplier-input"
                  id="lead-name"
                  autocomplete="name"
                  maxlength="64"
                  value="${esc(item?.customer_name === '未填写' ? '' : item?.customer_name || '')}"
                >
                ${fieldError('customer_name')}
              </div>
              <div class="supplier-field">
                <label for="lead-phone">客户手机号 ${requiredMark()}</label>
                <input
                  class="supplier-input"
                  id="lead-phone"
                  autocomplete="tel"
                  inputmode="tel"
                  maxlength="32"
                  placeholder="请输入 11 位手机号"
                  value="${esc(item?.phone || '')}"
                  aria-describedby="lead-phone-help"
                >
                <span class="supplier-help" id="lead-phone-help">${phoneHelp}</span>
                ${fieldError('phone')}
              </div>
            </div>
            <div class="supplier-grid">
              <div class="supplier-field">
                <label for="lead-city">服务城市 ${requiredMark()}</label>
                <select class="supplier-select" id="lead-city">
                  <option value="">请选择城市</option>
                  ${state.cities
                    .map(
                      (row) =>
                        `<option value="${row.code}" ${city?.code === row.code ? 'selected' : ''}>${esc(
                          row.name,
                        )}</option>`,
                    )
                    .join('')}
                </select>
                ${fieldError('city')}
                ${fieldError('region_code')}
              </div>
              <div class="supplier-field">
                <label for="lead-district">服务区县</label>
                <select class="supplier-select" id="lead-district">
                  <option value="">暂不确定 / 全市范围</option>
                  ${state.districts
                    .map(
                      (row) =>
                        `<option value="${row.code}" ${district?.code === row.code ? 'selected' : ''}>${esc(
                          row.name,
                        )}</option>`,
                    )
                    .join('')}
                </select>
              </div>
            </div>
          </section>

          <section class="supplier-form-section" aria-labelledby="need-section-title">
            <div class="supplier-form-section-head">
              <span class="supplier-step">2</span>
              <div>
                <h3 id="need-section-title">客户需求</h3>
                <p>信息越具体，平台越容易准确审核和派发</p>
              </div>
            </div>
            <div class="supplier-grid">
              <div class="supplier-field">
                <label for="lead-source">获客来源</label>
                <select class="supplier-select" id="lead-source">${selectOptions(
                  state.sourceOptions,
                  item?.source_channel || '供应商推荐',
                  '请选择获客来源',
                  '原有来源',
                )}</select>
              </div>
              <div class="supplier-field">
                <label for="lead-category">需求类型</label>
                <select class="supplier-select" id="lead-category">${selectOptions(
                  state.categoryOptions,
                  item?.category_code || '',
                  '请选择需求类型',
                  '原有类别',
                )}</select>
              </div>
            </div>
            <div class="supplier-field">
              <label for="lead-need">需求说明 ${requiredMark()}</label>
              <textarea
                class="supplier-textarea"
                id="lead-need"
                maxlength="2000"
                placeholder="请填写建房或装修地点、计划、时间等关键信息"
              >${esc(item?.need_summary || '')}</textarea>
              ${fieldError('need_summary')}
            </div>
            <div class="supplier-grid">
              <div class="supplier-field">
                <label for="lead-budget-min">预算最低（元）</label>
                <input
                  class="supplier-input"
                  id="lead-budget-min"
                  type="number"
                  min="0"
                  inputmode="numeric"
                  placeholder="选填"
                  value="${esc(item?.budget_min ?? '')}"
                >
                ${fieldError('budget_min')}
              </div>
              <div class="supplier-field">
                <label for="lead-budget-max">预算最高（元）</label>
                <input
                  class="supplier-input"
                  id="lead-budget-max"
                  type="number"
                  min="0"
                  inputmode="numeric"
                  placeholder="选填"
                  value="${esc(item?.budget_max ?? '')}"
                >
                ${fieldError('budget_max')}
              </div>
            </div>
          </section>

          <section class="supplier-form-section" aria-labelledby="consent-section-title">
            <div class="supplier-form-section-head">
              <span class="supplier-step">3</span>
              <div>
                <h3 id="consent-section-title">授权与提交</h3>
                <p>提交前请确认客户已知情</p>
              </div>
            </div>
            <label class="supplier-check" for="lead-consent">
              <input type="checkbox" id="lead-consent" ${item?.consent_confirmed ? 'checked' : ''}>
              <span>
                <b>我确认已获得客户授权 ${requiredMark()}</b>
                <small>客户知晓其联系方式和建房或装修需求将提交给合家美宅，用于业务对接。</small>
              </span>
            </label>
            ${fieldError('consent_confirmed')}
            <div class="supplier-notice supplier-privacy">
              平台会保护客户信息。相同手机号可能进入人工复核，是否通过及后续进度会在“我的客资”中更新。
            </div>
          </section>

          <div class="supplier-actions">
            <button type="button" class="supplier-btn" id="save-draft">保存草稿</button>
            <button type="button" class="supplier-btn primary" id="save-submit">提交平台审核</button>
          </div>
        </form>
      </section>
    `,
    { showHero: false },
  );

  document.querySelector('#return-to-list').onclick = () => {
    state.editing = null;
    state.tab = 'list';
    renderList();
  };
  document.querySelector('#lead-city').onchange = async (event) => {
    await loadDistricts(event.target.value);
    zsSetSafeHtml(
      document.querySelector('#lead-district'),
      '<option value="">暂不确定 / 全市范围</option>' +
        state.districts
          .map((row) => `<option value="${row.code}">${esc(row.name)}</option>`)
          .join(''),
    );
    clearFieldError('city');
    clearFieldError('region_code');
  };
  document.querySelector('#save-draft').onclick = () => saveForm(item, false);
  document.querySelector('#save-submit').onclick = () => saveForm(item, true);
  bindFieldErrorClearing();
}

function optionalNumber(selector) {
  const raw = value(selector);
  return raw === '' ? null : Number(raw);
}

function normalizePhone(input) {
  let digits = String(input || '').replace(/\D/g, '');
  if (digits.startsWith('86') && digits.length === 13) digits = digits.slice(2);
  return digits;
}

function formPayload() {
  const cityCode = value('#lead-city');
  const districtCode = value('#lead-district');
  const city = state.cities.find((row) => row.code === cityCode);
  const district = state.districts.find((row) => row.code === districtCode);
  return {
    customer_name: value('#lead-name'),
    phone: normalizePhone(value('#lead-phone')),
    city: city?.name || '',
    district: district?.name || '',
    region_code: districtCode || cityCode,
    source_channel: value('#lead-source'),
    category_code: value('#lead-category'),
    need_summary: value('#lead-need'),
    budget_min: optionalNumber('#lead-budget-min'),
    budget_max: optionalNumber('#lead-budget-max'),
    consent_confirmed: Boolean(document.querySelector('#lead-consent')?.checked),
  };
}

function validateDraft(payload) {
  const errors = {};
  if (payload.phone && !/^1\d{10}$/.test(payload.phone)) {
    errors.phone = '请填写 11 位手机号';
  }
  if (
    payload.budget_min !== null &&
    (Number.isNaN(payload.budget_min) || payload.budget_min < 0)
  ) {
    errors.budget_min = '请输入不小于 0 的有效金额';
  }
  if (
    payload.budget_max !== null &&
    (Number.isNaN(payload.budget_max) || payload.budget_max < 0)
  ) {
    errors.budget_max = '请输入不小于 0 的有效金额';
  }
  if (
    payload.budget_min !== null &&
    payload.budget_max !== null &&
    !errors.budget_min &&
    !errors.budget_max &&
    payload.budget_min > payload.budget_max
  ) {
    errors.budget_max = '最高预算不能低于最低预算';
  }
  return errors;
}

function validateSubmission(payload) {
  const errors = validateDraft(payload);
  if (!payload.customer_name || payload.customer_name === '未填写') {
    errors.customer_name = '请填写客户姓名';
  }
  if (!/^1\d{10}$/.test(payload.phone)) {
    errors.phone = '请填写 11 位手机号';
  }
  if (!payload.city) {
    errors.city = '请选择服务城市';
  } else if (!payload.region_code) {
    errors.region_code = '请选择服务城市';
  }
  if (!payload.need_summary) {
    errors.need_summary = '请填写客户需求';
  }
  if (!payload.consent_confirmed) {
    errors.consent_confirmed = '请确认已获得客户授权';
  }
  return errors;
}

function hasMeaningfulDraftData(payload) {
  return Boolean(
    payload.customer_name ||
      payload.phone ||
      payload.city ||
      payload.district ||
      payload.category_code ||
      payload.need_summary ||
      payload.budget_min !== null ||
      payload.budget_max !== null ||
      payload.consent_confirmed,
  );
}

function clearFieldError(name) {
  document.querySelectorAll(`[data-field-error="${name}"]`).forEach((element) => {
    element.textContent = '';
  });
  const control = document.querySelector(fieldControls[name]);
  if (control) control.removeAttribute('aria-invalid');
}

function clearFormErrors() {
  const summary = document.querySelector('#form-error-summary');
  if (summary) {
    summary.hidden = true;
    summary.textContent = '';
  }
  document.querySelectorAll('[data-field-error]').forEach((element) => {
    element.textContent = '';
  });
  document.querySelectorAll('[aria-invalid="true"]').forEach((control) => {
    control.removeAttribute('aria-invalid');
  });
}

function showFormErrors(errors) {
  clearFormErrors();
  const entries = Object.entries(errors || {}).filter(([, message]) => Boolean(message));
  if (!entries.length) return;
  entries.forEach(([name, message]) => {
    document.querySelectorAll(`[data-field-error="${name}"]`).forEach((element) => {
      element.textContent = message;
    });
    const control = document.querySelector(fieldControls[name]);
    if (control) control.setAttribute('aria-invalid', 'true');
  });
  const summary = document.querySelector('#form-error-summary');
  if (summary) {
    const fieldEntries = entries.filter(([name]) => name !== '__form');
    const summaryText = fieldEntries.length
      ? `还有 ${fieldEntries.length} 项需要完善，请查看标红位置。`
      : entries[0][1];
    summary.textContent = summaryText;
    summary.hidden = false;
    summary.focus();
    summary.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  const firstField = entries.find(([name]) => name !== '__form');
  if (firstField) {
    const control = document.querySelector(fieldControls[firstField[0]]);
    if (control) control.focus({ preventScroll: true });
  }
}

function bindFieldErrorClearing() {
  Object.entries(fieldControls).forEach(([name, selector]) => {
    const control = document.querySelector(selector);
    if (!control) return;
    const eventName = control.type === 'checkbox' || control.tagName === 'SELECT' ? 'change' : 'input';
    control.addEventListener(eventName, () => clearFieldError(name));
  });
}

function setFormBusy(busy) {
  const form = document.querySelector('#lead-form');
  if (!form) return;
  if (busy) form.dataset.busy = '1';
  else delete form.dataset.busy;
  form.querySelectorAll('button').forEach((button) => {
    button.disabled = busy;
  });
}

function serverFieldErrors(error) {
  const fields = error?.details?.fields;
  if (!fields || typeof fields !== 'object' || Array.isArray(fields)) return null;
  const result = { ...fields };
  if (result.city && result.region_code) delete result.region_code;
  return result;
}

async function saveForm(item, submitAfter) {
  const form = document.querySelector('#lead-form');
  if (!form || form.dataset.busy === '1') return;
  const payload = formPayload();
  if (submitAfter) {
    const errors = validateSubmission(payload);
    if (Object.keys(errors).length) {
      showFormErrors(errors);
      return;
    }
  } else {
    const errors = validateDraft(payload);
    if (Object.keys(errors).length) {
      showFormErrors(errors);
      return;
    }
  }
  if (!submitAfter && !hasMeaningfulDraftData(payload)) {
    showFormErrors({ __form: '请至少填写一项内容，再保存草稿。' });
    return;
  }
  clearFormErrors();
  setFormBusy(true);
  let saved = item;
  try {
    if (item) {
      saved = await api(`/v1.2/supplier/leads/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
    } else {
      saved = await api('/v1.2/supplier/leads', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    }
    if (submitAfter) {
      await api(`/v1.2/supplier/leads/${saved.id}/submit`, { method: 'POST' });
      toast('已提交，平台正在审核');
    } else {
      toast('草稿已保存');
    }
    state.editing = null;
    state.tab = 'list';
    state.listPage = 1;
    await renderList();
  } catch (error) {
    if (submitAfter && saved?.id && !item) {
      state.editing = saved;
      await renderUpload(saved);
    }
    const fields = serverFieldErrors(error);
    showFormErrors(fields || { __form: error.message || '保存失败，请稍后重试。' });
    toast(error.message || '保存失败，请稍后重试', 'error');
  } finally {
    setFormBusy(false);
  }
}

async function deleteDraft(id) {
  openSheet(
    '删除这份草稿？',
    `
      <p class="supplier-sheet-copy">删除后无法恢复，已经提交审核的客资不会受到影响。</p>
      <div class="supplier-sheet-actions">
        <button class="supplier-btn" id="cancel-delete">保留草稿</button>
        <button class="supplier-btn danger" id="confirm-delete">确认删除</button>
      </div>
    `,
  );
  document.querySelector('#cancel-delete').onclick = closeSheet;
  document.querySelector('#confirm-delete').onclick = async (event) => {
    if (event.currentTarget.dataset.busy === '1') return;
    event.currentTarget.dataset.busy = '1';
    event.currentTarget.disabled = true;
    try {
      await api(`/v1.2/supplier/leads/${id}`, { method: 'DELETE' });
      closeSheet();
      toast('草稿已删除');
      state.listPage = 1;
      await renderList();
    } catch (error) {
      delete event.currentTarget.dataset.busy;
      event.currentTarget.disabled = false;
      toast(error.message, 'error');
    }
  };
}

async function reviseLead(id) {
  openSheet(
    '修改后重新提交',
    `
      <p class="supplier-sheet-copy">客资会恢复为草稿。请根据平台说明修改，确认无误后再次提交审核。</p>
      <button class="supplier-btn primary block" id="confirm-revise">开始修改</button>
    `,
  );
  document.querySelector('#confirm-revise').onclick = async (event) => {
    if (event.currentTarget.dataset.busy === '1') return;
    event.currentTarget.dataset.busy = '1';
    event.currentTarget.disabled = true;
    try {
      const item = await api(`/v1.2/supplier/leads/${id}/revise`, {
        method: 'POST',
      });
      closeSheet();
      state.editing = item;
      state.tab = 'upload';
      await renderUpload(item);
    } catch (error) {
      delete event.currentTarget.dataset.busy;
      event.currentTarget.disabled = false;
      toast(error.message, 'error');
    }
  };
}

async function showDetail(id) {
  try {
    const item = await api(`/v1.2/supplier/leads/${id}`);
    const fields = [
      ['客户姓名', item.customer_name === '未填写' ? '未填写' : item.customer_name],
      ['联系电话', item.phone || item.phone_masked],
      ['服务地区', `${item.city || ''} ${item.district || ''}`.trim()],
      ['获客来源', readableLabel(item.source_channel, '未填写')],
      ['需求类型', readableLabel(item.category_code, '未填写')],
      ['客户需求', item.need_summary],
      ['授权确认', item.consent_confirmed ? '已确认' : '未确认'],
      ['当前进度', readableLabel(item.status)],
      ['资料审核', readableLabel(item.review_status)],
      ['重复情况', item.duplicate_status ? labels[item.duplicate_status] || '平台复核中' : null],
      ['提交时间', fmt(item.submitted_at)],
      ['最后更新', fmt(item.updated_at)],
    ].filter(([, itemValue]) => itemValue !== null && itemValue !== undefined && itemValue !== '');
    const notice = item.review_note
      ? `<div class="supplier-error supplier-review-note"><b>平台说明</b><span>${esc(
          item.review_note,
        )}</span></div>`
      : '';
    let actions = '';
    if (item.status === 'DRAFT') {
      actions = `
        <div class="supplier-sheet-actions">
          <button class="supplier-btn primary" id="detail-edit">继续填写</button>
          <button class="supplier-btn danger" id="detail-delete">删除草稿</button>
        </div>
      `;
    } else if (item.status === 'INVALID' && item.review_status === 'REJECTED') {
      actions = '<button class="supplier-btn primary block" id="detail-revise">修改后重新提交</button>';
    }
    openSheet(
      '客资详情',
      `
        ${notice}
        <dl class="supplier-detail">
          ${fields
            .map(
              ([name, itemValue]) =>
                `<dt>${esc(name)}</dt><dd>${esc(itemValue || '--')}</dd>`,
            )
            .join('')}
        </dl>
        ${actions}
      `,
    );
    const edit = document.querySelector('#detail-edit');
    if (edit) {
      edit.onclick = () => {
        closeSheet();
        editLead(item.id);
      };
    }
    const remove = document.querySelector('#detail-delete');
    if (remove) remove.onclick = () => deleteDraft(item.id);
    const revise = document.querySelector('#detail-revise');
    if (revise) revise.onclick = () => reviseLead(item.id);
  } catch (error) {
    toast(error.message, 'error');
  }
}

boot();
