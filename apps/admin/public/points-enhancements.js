(() => {
  const nativeFetch = window.fetch.bind(window);
  let rechargeConfirmed = false;

  function toast(message) {
    const box = document.querySelector('#toast');
    if (!box) return;
    box.textContent = message;
    box.className = 'toast show error';
    setTimeout(() => { box.className = 'toast'; }, 2600);
  }

  function readOptionalDate(id) {
    const value = document.querySelector(id)?.value;
    return value ? new Date(value).toISOString() : null;
  }

  window.fetch = async function pointsEnhancedFetch(input, init = {}) {
    const url = typeof input === 'string' ? input : input.url;
    const method = String(init.method || 'GET').toUpperCase();
    if (method === 'POST' && url.includes('/api/v1/points/recharge') && init.body) {
      const body = JSON.parse(init.body);
      body.confirmed = rechargeConfirmed;
      rechargeConfirmed = false;
      return nativeFetch(input, { ...init, body: JSON.stringify(body) });
    }
    if (method === 'POST' && url.includes('/api/v1/points/packages') && init.body) {
      const body = JSON.parse(init.body);
      const entitlementsText = document.querySelector('#p-entitlements')?.value.trim() || '{}';
      body.entitlements = JSON.parse(entitlementsText);
      body.effective_at = readOptionalDate('#p-effective-at');
      body.expires_at = readOptionalDate('#p-expires-at');
      return nativeFetch(input, { ...init, body: JSON.stringify(body) });
    }
    return nativeFetch(input, init);
  };

  function injectPackageFields() {
    const save = document.querySelector('#save-package');
    const level = document.querySelector('#p-level');
    if (!save || !level || document.querySelector('#p-entitlements')) return;
    const host = level.closest('.field') || level.parentElement;
    const block = document.createElement('div');
    block.className = 'p1-package-fields';
    block.innerHTML = `
      <div class="field"><label for="p-entitlements">等级权益（JSON）</label><textarea id="p-entitlements" class="textarea" style="width:100%">{"客资价格权益":"按已发布规则","服务优先级":"标准"}</textarea><small>用于加盟商积分中心展示，建议使用简短键值对。</small></div>
      <div class="p1-date-grid"><div class="field"><label for="p-effective-at">生效时间</label><input id="p-effective-at" class="input" type="datetime-local"></div><div class="field"><label for="p-expires-at">失效时间</label><input id="p-expires-at" class="input" type="datetime-local"></div></div>`;
    host.insertAdjacentElement('afterend', block);
  }

  document.addEventListener('click', event => {
    const rechargeButton = event.target.closest('#do-recharge');
    if (rechargeButton) {
      const reference = document.querySelector('#rc-reference')?.value.trim() || '';
      if (!reference) return;
      const accepted = window.confirm(`请再次确认：线下款项已经核实，付款流水号为 ${reference}。确认后积分将立即入账且只能通过冲正修正。`);
      if (!accepted) {
        rechargeConfirmed = false;
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
      rechargeConfirmed = true;
    }
    const packageButton = event.target.closest('#save-package');
    if (packageButton) {
      try {
        const entitlements = JSON.parse(document.querySelector('#p-entitlements')?.value || '{}');
        if (!entitlements || Array.isArray(entitlements) || typeof entitlements !== 'object') throw new Error('权益必须为JSON对象');
        const start = document.querySelector('#p-effective-at')?.value;
        const end = document.querySelector('#p-expires-at')?.value;
        if (start && end && new Date(start) >= new Date(end)) throw new Error('生效时间必须早于失效时间');
      } catch (error) {
        event.preventDefault();
        event.stopImmediatePropagation();
        toast(error.message || '等级权益JSON格式错误');
      }
    }
  }, true);

  const observer = new MutationObserver(injectPackageFields);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  injectPackageFields();
})();
