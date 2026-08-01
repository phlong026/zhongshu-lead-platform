(() => {
  const API_PREFIX = '/api/v1';
  let rendering = false;

  const escapeHtml = (value = '') => String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));

  async function getJson(path) {
    const response = await fetch(`${API_PREFIX}${path}`, { credentials: 'include' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.code !== 'OK') throw new Error(payload.message || '请求失败');
    return payload.data;
  }

  function renderLowPointsNotice(account) {
    document.querySelectorAll('.p1-low-points-notice').forEach(node => node.remove());
    if (!account?.low_points) return;
    const hero = document.querySelector('main.content .hero');
    if (!hero) return;
    const notice = document.createElement('section');
    notice.className = 'p1-low-points-notice';
    notice.setAttribute('role', 'status');
    notice.innerHTML = `
      <div><b>积分余额偏低</b><span>当前 ${Number(account.balance || 0).toLocaleString('zh-CN')} 分，低于预警值 ${Number(account.low_points_threshold || 1000).toLocaleString('zh-CN')} 分。</span></div>
      <small>积分不足一条客资价格时将无法领取，请联系平台完成线下充值。</small>`;
    hero.insertAdjacentElement('afterend', notice);
  }

  function renderEntitlements(account) {
    if (document.querySelector('.p1-entitlements-card')) return;
    const title = [...document.querySelectorAll('.page-title')].find(node => node.textContent.includes('积分中心'));
    if (!title) return;
    const hero = document.querySelector('main.content .hero');
    if (!hero) return;
    const entries = Object.entries(account.level_entitlements || {});
    const card = document.createElement('section');
    card.className = 'card p1-entitlements-card';
    card.innerHTML = `
      <div class="card-title"><h3>${escapeHtml(account.level_code || 'V1')} 会员权益</h3><span class="badge badge-warning">档位 v${escapeHtml(account.level_package?.version || 1)}</span></div>
      ${entries.length ? `<div class="p1-entitlements-grid">${entries.map(([name, value]) => `<div><span>${escapeHtml(name)}</span><b>${escapeHtml(value)}</b></div>`).join('')}</div>` : '<p class="subtitle">当前等级暂无额外权益，具体权益由平台线下合作方案确定。</p>'}
      <p class="help">充值档位、赠送积分与会员权益均以平台已发布版本为准。</p>`;
    hero.insertAdjacentElement('afterend', card);
  }

  async function enhance() {
    if (rendering || !document.querySelector('main.content')) return;
    const isRelevant = document.querySelector('.page-title')?.textContent.includes('积分') || document.querySelector('.balance');
    if (!isRelevant) return;
    rendering = true;
    try {
      const me = await getJson('/auth/me');
      if (!me?.company_id) return;
      const account = await getJson(`/points/accounts/${encodeURIComponent(me.company_id)}`);
      renderLowPointsNotice(account);
      renderEntitlements(account);
    } catch {
      // 主页面已有统一错误处理；增强层失败不阻断核心业务。
    } finally {
      rendering = false;
    }
  }

  const observer = new MutationObserver(() => queueMicrotask(enhance));
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('hashchange', () => setTimeout(enhance, 0));
  enhance();
})();
