function zsEscape(value = '') {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
}

function zsBudget(snapshot = {}) {
  const min = Number(snapshot.budget_min || 0);
  const max = Number(snapshot.budget_max || 0);
  if (!min && !max) return '预算待确认';
  const format = value => value >= 10000 ? `${Math.round(value / 10000)} 万` : `${value} 元`;
  if (min && max) return `预算 ${format(min)}–${format(max)}`;
  return `预算 ${format(min || max)} 起`;
}

async function zsFetchLeadAssignments() {
  const query = new URLSearchParams(location.hash.split('?')[1] || '');
  const status = query.get('status') || '';
  const url = `/api/v1/dispatch/assignments?page=1&page_size=100${status ? `&status=${encodeURIComponent(status)}` : ''}`;
  try {
    const response = await fetch(url, { credentials: 'include' });
    const payload = await response.json();
    if (!response.ok || payload.code !== 'OK') return [];
    return payload.data?.items || [];
  } catch {
    return [];
  }
}

function zsApplyLeadFilters(wrapper) {
  const keyword = (wrapper.querySelector('[data-zs-search]')?.value || '').trim().toLowerCase();
  const region = wrapper.querySelector('[data-zs-region]')?.value || '';
  const source = wrapper.querySelector('[data-zs-source]')?.value || '';
  const time = wrapper.querySelector('[data-zs-time]')?.value || '';
  const now = Date.now();
  wrapper.querySelectorAll('.lead-card[data-assignment]').forEach(card => {
    const searchable = (card.dataset.search || card.textContent || '').toLowerCase();
    const assignedAt = Date.parse(card.dataset.assignedAt || '');
    const dayAge = Number.isFinite(assignedAt) ? (now - assignedAt) / 86400000 : 0;
    const timeMatch = !time || (time === 'TODAY' && dayAge <= 1) || (time === '7D' && dayAge <= 7) || (time === '30D' && dayAge <= 30);
    const visible = (!keyword || searchable.includes(keyword)) && (!region || card.dataset.region === region) && (!source || card.dataset.source === source) && timeMatch;
    card.hidden = !visible;
  });
}

function zsPopulateSelect(select, values) {
  if (!select) return;
  const label = select.dataset.defaultLabel || '全部';
  select.innerHTML = `<option value="">${zsEscape(label)}</option>${values.map(value => `<option value="${zsEscape(value)}">${zsEscape(value)}</option>`).join('')}`;
}

function zsDecorateLeadCards(wrapper, assignments) {
  const byId = new Map(assignments.map(item => [String(item.id), item]));
  const regions = new Set();
  const sources = new Set();
  wrapper.querySelectorAll('.lead-card[data-assignment]').forEach(card => {
    const item = byId.get(String(card.dataset.assignment));
    if (!item) return;
    const snapshot = item.lead_snapshot || {};
    const region = [snapshot.city, snapshot.district].filter(Boolean).join(' ');
    const source = snapshot.source_channel || '其他来源';
    if (region) regions.add(region);
    if (source) sources.add(source);
    card.dataset.region = region;
    card.dataset.source = source;
    card.dataset.assignedAt = item.assigned_at || '';
    card.dataset.search = [snapshot.customer_name, region, source, snapshot.category_code, snapshot.need_summary].filter(Boolean).join(' ');
    card.classList.add('zs-v13-lead-card');
    const paragraph = card.querySelector('p');
    if (paragraph) paragraph.textContent = `${region || '地区待确认'} · ${source}`;
    let need = card.querySelector('.zs-v13-lead-need');
    if (!need) {
      need = document.createElement('p');
      need.className = 'zs-v13-lead-need';
      const footer = card.querySelector('.line:last-child');
      card.insertBefore(need, footer || null);
    }
    need.textContent = `${snapshot.category_code || '需求待核实'} · ${zsBudget(snapshot)}`;
    const time = card.querySelector('.zs-v13-assigned-time');
    if (!time) {
      const stamp = document.createElement('small');
      stamp.className = 'zs-v13-assigned-time';
      stamp.textContent = item.assigned_at ? new Date(item.assigned_at).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' }) : '';
      card.querySelector('.line:first-child')?.appendChild(stamp);
    }
  });
  zsPopulateSelect(wrapper.querySelector('[data-zs-region]'), [...regions].sort());
  zsPopulateSelect(wrapper.querySelector('[data-zs-source]'), [...sources].sort());
  zsApplyLeadFilters(wrapper);
}

async function zsPatchLeadList() {
  if (!/^#\/leads(?:\?|$)/.test(location.hash || '')) return;
  const main = document.querySelector('main.content');
  if (!main || main.dataset.zsV13Leads === '1') return;
  const title = main.querySelector(':scope > .page-title');
  const subtitle = main.querySelector(':scope > .subtitle');
  const tabs = main.querySelector(':scope > .tabs');
  const list = main.querySelector(':scope > .list');
  if (!title || !tabs || !list) return;

  const wrapper = document.createElement('div');
  wrapper.className = 'zs-v13-leads-page';
  const heading = document.createElement('div');
  heading.className = 'zs-v13-leads-heading';
  heading.innerHTML = `<div><h1>${zsEscape(title.textContent || '我的客资')}</h1><p>仅显示派发给当前加盟商公司的客资</p></div><button type="button" class="zs-v13-filter-trigger" aria-label="筛选">⌕ 筛选</button>`;
  const search = document.createElement('label');
  search.className = 'zs-v13-search';
  search.innerHTML = '<span>⌕</span><input type="search" data-zs-search placeholder="搜索客户姓名 / 地区 / 来源">';
  const filters = document.createElement('div');
  filters.className = 'zs-v13-filter-row';
  filters.innerHTML = `
    <select data-zs-region data-default-label="全部区域" aria-label="地区筛选"><option value="">全部区域</option></select>
    <select data-zs-source data-default-label="全部来源" aria-label="来源筛选"><option value="">全部来源</option></select>
    <select data-zs-time aria-label="时间筛选"><option value="">全部时间</option><option value="TODAY">今天</option><option value="7D">近7天</option><option value="30D">近30天</option></select>`;
  const reminder = document.createElement('div');
  reminder.className = 'zs-v13-reminder';
  reminder.innerHTML = '<b>!</b><span>24小时未领取将再次提醒，48小时自动回收</span>';

  title.remove();
  subtitle?.remove();
  wrapper.append(heading, tabs, search, filters, reminder, list);
  main.appendChild(wrapper);
  main.dataset.zsV13Leads = '1';

  const runFilter = () => zsApplyLeadFilters(wrapper);
  wrapper.querySelector('[data-zs-search]')?.addEventListener('input', runFilter);
  wrapper.querySelectorAll('select').forEach(select => select.addEventListener('change', runFilter));
  wrapper.querySelector('.zs-v13-filter-trigger')?.addEventListener('click', () => wrapper.querySelector('[data-zs-region]')?.focus());
  const assignments = await zsFetchLeadAssignments();
  if (main.dataset.zsV13Leads === '1' && document.contains(wrapper)) zsDecorateLeadCards(wrapper, assignments);
}
const zsLeadListObserver = new MutationObserver(() => zsPatchLeadList());
zsLeadListObserver.observe(document.documentElement, { childList: true, subtree: true });
window.addEventListener('hashchange', () => queueMicrotask(zsPatchLeadList));
zsPatchLeadList();
