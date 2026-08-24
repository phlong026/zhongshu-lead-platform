const ZS_V13_HOME_MARKER = 'zsV13Home';

function zsText(node, fallback = '') {
  return (node?.textContent || fallback).trim();
}

function zsRoute(route) {
  location.hash = `#/${route}`;
}

function zsIcon(name) {
  return window.ZSIconSystem?.svg(name) || '';
}

function zsPatchTopbar() {
  const brandCopy = document.querySelector('.topbar .brand > div');
  if (brandCopy && brandCopy.dataset.zsV13 !== '1') {
    const small = brandCopy.querySelector('small');
    const titleNode = [...brandCopy.childNodes].find(node => node.nodeType === Node.TEXT_NODE);
    if (titleNode) titleNode.nodeValue = '合家美宅';
    small?.remove();
    brandCopy.dataset.zsV13 = '1';
  }
}

function zsCreateQuickActions() {
  const section = document.createElement('section');
  section.className = 'zs-v13-quick';
  zsSetSafeHtml(section, `
    <div class="zs-v13-section-head"><h3>快捷入口</h3></div>
    <div class="zs-v13-actions">
      <button class="zs-v13-action" data-zs-route="leads"><i>${zsIcon('list')}</i><span>我的客资</span></button>
      <button class="zs-v13-action" data-zs-route="points"><i>${zsIcon('coins')}</i><span>积分中心</span></button>
      <button class="zs-v13-action" data-zs-route="leads?status=FOLLOWING"><i>${zsIcon('clipboard-check')}</i><span>跟进记录</span></button>
    </div>`);
  return section;
}

function zsPatchHome() {
  if (!/^#\/(home)?(?:\?|$)/.test(location.hash || '#/home')) return;
  const main = document.querySelector('main.content');
  if (!main || main.dataset[ZS_V13_HOME_MARKER] === '1') return;
  const title = main.querySelector(':scope > .page-title');
  const subtitle = main.querySelector(':scope > .subtitle');
  const hero = main.querySelector(':scope > .hero');
  const metrics = main.querySelector(':scope > .metrics');
  const cards = [...main.querySelectorAll(':scope > .card')];
  if (!title || !subtitle || !hero || !metrics || !cards.length) return;

  const originalTitle = zsText(title, '您好');
  const companyText = zsText(subtitle, '加盟商');
  const levelName = companyText.match(/(?:普通|重点|核心)加盟商/)?.[0]
    || ({ V1: '普通加盟商', V2: '重点加盟商', V3: '核心加盟商' }[companyText.match(/\bV[123]\b/i)?.[0]?.toUpperCase()])
    || '普通加盟商';
  const company = companyText.replace(/\s*[·•]\s*(?:(?:普通|重点|核心)加盟商|V[123]\s*会员?)/i, '').trim();

  const identity = document.createElement('section');
  identity.className = 'zs-v13-identity';
  zsSetSafeHtml(identity, `
    <div class="zs-v13-avatar" aria-hidden="true"></div>
    <div class="zs-v13-identity-copy">
      <h1>${originalTitle}</h1>
      <p>${company || '加盟商公司'}</p>
    </div>
    <span class="zs-v13-level">${levelName}</span>`);

  const heroButton = hero.querySelector('[data-route="points"]');
  if (heroButton) heroButton.textContent = '去充值';
  hero.classList.add('zs-v13-point-card');
  metrics.classList.add('zs-v13-metrics');

  const leadCard = cards.find(card => /待处理客资/.test(card.textContent || '')) || cards[0];
  leadCard.classList.add('zs-v13-lead-section');
  const noteCard = cards.find(card => card !== leadCard);
  if (noteCard) noteCard.classList.add('zs-v13-note');

  const wrapper = document.createElement('div');
  wrapper.className = 'zs-v13-home';
  wrapper.append(identity, hero, metrics, zsCreateQuickActions(), leadCard);
  if (noteCard) wrapper.append(noteCard);
  title.remove();
  subtitle.remove();
  main.appendChild(wrapper);
  main.dataset[ZS_V13_HOME_MARKER] = '1';
}

function zsPatchPage() {
  zsPatchTopbar();
  zsPatchHome();
}

const zsObserver = new MutationObserver(zsPatchPage);
zsObserver.observe(document.documentElement, { childList: true, subtree: true });
document.addEventListener('click', event => {
  const action = event.target.closest('[data-zs-route]');
  if (!action) return;
  event.preventDefault();
  zsRoute(action.dataset.zsRoute);
});
window.addEventListener('hashchange', () => queueMicrotask(zsPatchPage));
zsPatchPage();
