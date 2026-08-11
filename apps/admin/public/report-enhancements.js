(() => {
  const API_PREFIX = '/api/v1';
  let loading = false;

  const escapeHtml = (value = '') => String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
  const number = value => Number(value || 0).toLocaleString('zh-CN');

  async function getPerformance(days = 30) {
    const response = await fetch(`${API_PREFIX}/dashboard/performance?days=${days}`, { credentials: 'include' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.code !== 'OK') throw new Error(payload.message || '经营报表加载失败');
    return payload.data;
  }

  function render(data) {
    document.querySelector('.p1-performance-report')?.remove();
    const dashboardTitle = [...document.querySelectorAll('h1')].find(node => node.textContent.includes('运营数据看板'));
    if (!dashboardTitle) return;
    const alertsPanel = [...document.querySelectorAll('.panel')].find(node => node.textContent.includes('运营预警'));
    const funnel = data.funnel || {};
    const finance = data.finance;
    const report = document.createElement('section');
    report.className = 'p1-performance-report';
    zsSetSafeHtml(report, `
      <div class="panel-head"><div><h3>近 ${number(data.days)} 日经营漏斗</h3><p>领取率、跟进率和转化率由服务端统一口径计算。</p></div></div>
      <div class="p1-report-cards">
        ${[['新增客资',funnel.leads_created],['合格客资',funnel.qualified],['人工派发',funnel.assignments],['已领取',funnel.claimed],['已跟进',funnel.followed],['已成交',funnel.completed]].map(([label,value]) => `<div><span>${label}</span><b>${number(value)}</b></div>`).join('')}
      </div>
      <div class="p1-rate-cards">
        ${[['核验通过率',funnel.qualification_rate],['领取率',funnel.claim_rate],['跟进率',funnel.followup_rate],['成交转化率',funnel.conversion_rate],['退回率',funnel.return_rate]].map(([label,value]) => `<div><span>${label}</span><b>${number(value)}%</b></div>`).join('')}
      </div>
      ${finance ? `<div class="p1-finance-strip"><div><span>充值积分</span><b>${number(finance.points_recharged)}</b></div><div><span>消耗积分</span><b>${number(finance.points_consumed)}</b></div><div><span>返还积分</span><b>${number(finance.points_refunded)}</b></div><div><span>净积分变化</span><b>${number(finance.net_points_change)}</b></div></div>` : ''}
      <div class="p1-region-table"><h3>区域经营表现</h3><div class="p1-region-head"><span>区域</span><span>客资</span><span>派发</span><span>成交</span><span>转化率</span></div>${(data.regions || []).slice(0, 10).map(item => `<div><strong>${escapeHtml(item.region)}</strong><span>${number(item.leads)}</span><span>${number(item.assignments)}</span><span>${number(item.completed)}</span><span>${number(item.conversion_rate)}%</span></div>`).join('') || '<p>暂无区域数据</p>'}</div>`);
    if (alertsPanel) alertsPanel.insertAdjacentElement('beforebegin', report);
    else document.querySelector('main')?.appendChild(report);
  }

  async function enhance() {
    if (loading || document.querySelector('.p1-performance-report')) return;
    const dashboardTitle = [...document.querySelectorAll('h1')].find(node => node.textContent.includes('运营数据看板'));
    if (!dashboardTitle) return;
    loading = true;
    try { render(await getPerformance()); } catch { /* 权限或网络错误不影响原看板 */ }
    finally { loading = false; }
  }

  const observer = new MutationObserver(() => queueMicrotask(enhance));
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('hashchange', () => setTimeout(enhance, 0));
  enhance();
})();
