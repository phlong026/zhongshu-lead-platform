(() => {
  const ICONS = {
    home:'<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-6h6v6"/>',
    list:'<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
    gem:'<path d="m12 2 7 5-7 15L5 7l7-5Z"/><path d="m5 7 7 4 7-4M9 4l3 7 3-7"/>',
    bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
    user:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    inbox:'<path d="M4 4h16v16H4z"/><path d="M4 14h4l2 3h4l2-3h4"/><path d="M12 3v8m0 0 3-3m-3 3-3-3"/>',
    phone:'<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.9.33 1.78.62 2.63a2 2 0 0 1-.45 2.11L8 9.73a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.85.29 1.73.5 2.63.62A2 2 0 0 1 22 16.92Z"/>',
    'circle-check':'<circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/>',
    send:'<path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/>',
    users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    settings:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06-2.12 2.12-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V20h-3v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06-2.12-2.12.06-.06A1.65 1.65 0 0 0 7.2 15a1.65 1.65 0 0 0-1.51-1H5.6v-3h.09A1.65 1.65 0 0 0 7.2 10a1.65 1.65 0 0 0-.33-1.82l-.06-.06L8.93 6l.06.06A1.65 1.65 0 0 0 10.81 6a1.65 1.65 0 0 0 1-1.51V4.4h3v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06 2.12 2.12-.06.06A1.65 1.65 0 0 0 19.4 10a1.65 1.65 0 0 0 1.51 1H21v3h-.09A1.65 1.65 0 0 0 19.4 15Z"/>',
    activity:'<path d="M3 12h4l2-7 4 14 2-7h6"/>',
    plus:'<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
    receipt:'<path d="M6 2h12v20l-3-2-3 2-3-2-3 2V2Z"/><path d="M9 7h6M9 11h6M9 15h4"/>',
    'rotate-ccw':'<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'alert-triangle':'<path d="M10.3 3.8 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.8a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
    x:'<path d="m6 6 12 12M18 6 6 18"/>',
    'chevron-left':'<path d="m15 18-6-6 6-6"/>',
    'chevron-right':'<path d="m9 18 6-6-6-6"/>',
    menu:'<path d="M4 7h16M4 12h16M4 17h16"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    'help-circle':'<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.7 2.7 0 1 1 4.2 2.3c-1 .6-1.7 1.1-1.7 2.2M12 17h.01"/>',
    play:'<circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4V8Z"/>',
    'link-off':'<path d="m9 17-1 1a4 4 0 0 1-6-6l3-3a4 4 0 0 1 5-.5M15 7l1-1a4 4 0 0 1 6 6l-3 3a4 4 0 0 1-5 .5M8 12h3M13 12h3M3 3l18 18"/>',
    'external-link':'<path d="M14 3h7v7M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
    building:'<path d="M4 21V5l8-3 8 3v16M9 21v-4h6v4M8 7h.01M12 7h.01M16 7h.01M8 11h.01M12 11h.01M16 11h.01"/>',
    'layout-dashboard':'<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    'badge-check':'<path d="m12 2 3 2 3.5-.3.8 3.4 2.7 2.2-1.5 3.2 1.5 3.2-2.7 2.2-.8 3.4L15 20l-3 2-3-2-3.5.3-.8-3.4L2 14.7l1.5-3.2L2 8.3l2.7-2.2.8-3.4L9 4l3-2Z"/><path d="m8.5 12 2 2 5-5"/>',
    'clipboard-check':'<path d="M9 5h6M9 3h6v4H9z"/><path d="M7 5H5v16h14V5h-2M8 14l2 2 5-5"/>',
    'file-text':'<path d="M6 2h8l4 4v16H6z"/><path d="M14 2v5h5M9 13h6M9 17h6M9 9h2"/>',
    wallet:'<path d="M3 6h16a2 2 0 0 1 2 2v11H3V6Z"/><path d="M3 6V4h14v2M16 12h5"/>',
    'shield-check':'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
    filter:'<path d="M4 5h16M7 12h10M10 19h4"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'
  };

  const GLYPH_MAP = {
    '⌂':'home','▤':'list','◈':'gem','◉':'bell','♙':'user','⇩':'inbox','☎':'phone','✓':'circle-check',
    '↗':'external-link','♟':'users','⚙':'settings','⌁':'link-off','＋':'plus','+':'plus','≋':'receipt','↩':'rotate-ccw',
    '◇':'gem','◷':'clock','!':'alert-triangle','×':'x','‹':'chevron-left','›':'chevron-right','☰':'menu','⌕':'search',
    '?':'help-circle','▶':'play','●':'circle-check','↻':'rotate-ccw'
  };

  const ROUTE_MAP = {
    home:'home',leads:'list',points:'gem',notifications:'bell',profile:'user',login:'shield-check',
    dashboard:'layout-dashboard',staging:'inbox',verification:'phone',qualified:'badge-check',assignments:'external-link',
    companies:'building',recharge:'plus',ledgers:'receipt',returns:'rotate-ccw',outbox:'bell',users:'users',configs:'settings',
    audit:'activity','master-data':'database'
  };

  function svg(name, className='zs-svg-icon') {
    const body = ICONS[name] || ICONS.info;
    return `<svg class="${className}" data-icon="${name}" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
  }

  function contextName(el, glyph) {
    const routeEl = el.closest('[data-route],[data-adm-extra-route]');
    const route = routeEl?.dataset.route || routeEl?.dataset.admExtraRoute;
    if (route && ROUTE_MAP[route]) return ROUTE_MAP[route];
    const text = `${el.parentElement?.textContent || ''} ${el.closest('button,a,article,section,div')?.textContent || ''}`;
    if (/公司资料|加盟商|企业/.test(text)) return 'building';
    if (/账户|个人|我的/.test(text)) return 'user';
    if (/帮助/.test(text)) return 'help-circle';
    if (/跟进/.test(text)) return 'clipboard-check';
    if (/消息|通知/.test(text)) return 'bell';
    if (/积分|余额|充值/.test(text)) return glyph === '＋' || glyph === '+' ? 'plus' : 'gem';
    if (/客资|订单|列表/.test(text)) return 'list';
    if (/退回|回收/.test(text)) return 'rotate-ccw';
    if (/拨打|电话|核验/.test(text)) return 'phone';
    if (/导入|暂存/.test(text)) return 'inbox';
    if (/派发|发送/.test(text)) return 'external-link';
    if (/搜索/.test(text)) return 'search';
    if (/筛选/.test(text)) return 'filter';
    if (/成功|通过|完成/.test(text) && glyph === '✓') return 'circle-check';
    return GLYPH_MAP[glyph] || 'info';
  }

  function replaceLeaf(el) {
    if (!(el instanceof Element) || el.dataset.zsSvgIcon === '1' || el.querySelector('svg')) return;
    const raw = (el.textContent || '').trim();
    if (!raw) return;
    if (raw === '‹ 返回') {
      el.innerHTML = `${svg('chevron-left')}<span>返回</span>`;
      el.dataset.zsSvgIcon = '1';
      el.classList.add('zs-icon-label');
      return;
    }
    if (/^.+\s›$/.test(raw) && raw.length < 24) {
      const label = raw.replace(/\s›$/, '');
      el.innerHTML = `<span>${label}</span>${svg('chevron-right')}`;
      el.dataset.zsSvgIcon = '1';
      el.classList.add('zs-icon-label');
      return;
    }
    const name = GLYPH_MAP[raw];
    if (!name) return;
    el.innerHTML = svg(contextName(el, raw));
    el.dataset.zsSvgIcon = '1';
    el.classList.add('zs-svg-icon-wrap');
  }

  function decorate(root=document) {
    const scope = root instanceof Element || root instanceof Document ? root : document;
    const leaves = scope.querySelectorAll('*');
    for (const el of leaves) {
      if (el.children.length === 0) replaceLeaf(el);
    }
    if (scope instanceof Element && scope.children.length === 0) replaceLeaf(scope);
  }

  let queued = false;
  const observer = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    queueMicrotask(() => { queued = false; decorate(document); });
  });
  observer.observe(document.documentElement, {childList:true, subtree:true});
  document.addEventListener('DOMContentLoaded', () => decorate(document));
  decorate(document);
  window.ZSIconSystem = {svg, decorate, icons:Object.keys(ICONS), glyphs:{...GLYPH_MAP}};
})();
