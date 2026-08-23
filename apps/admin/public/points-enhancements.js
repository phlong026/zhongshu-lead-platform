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

  window.fetch = async function pointsEnhancedFetch(input, init = {}) {
    const url = typeof input === 'string' ? input : input.url;
    const method = String(init.method || 'GET').toUpperCase();
    if (method === 'POST' && url.includes('/api/v1/points/recharge') && init.body) {
      const body = JSON.parse(init.body);
      body.confirmed = rechargeConfirmed;
      rechargeConfirmed = false;
      return nativeFetch(input, { ...init, body: JSON.stringify(body) });
    }
    return nativeFetch(input, init);
  };

  document.addEventListener('click', event => {
    const rechargeButton = event.target.closest('#do-recharge');
    if (!rechargeButton) return;
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
  }, true);
})();
