function zsDetailRouteActive() {
  return /^#\/lead\/[^/?]+/.test(location.hash || '');
}

function zsSyncDetailRouteClass() {
  document.body.classList.toggle('zs-v13-detail-route', zsDetailRouteActive());
}

function zsFindDetailRow(card, label) {
  return [...(card?.querySelectorAll('.detail-row') || [])].find(row => row.querySelector('dt')?.textContent.trim() === label);
}

function zsPatchLeadDetail() {
  zsSyncDetailRouteClass();
  if (!zsDetailRouteActive()) return;
  const main = document.querySelector('main.content');
  if (!main || main.dataset.zsV13Detail === '1') return;
  const back = main.querySelector(':scope > .icon-btn');
  const title = main.querySelector(':scope > .page-title');
  const hero = main.querySelector(':scope > .hero');
  const cards = [...main.querySelectorAll(':scope > .card')];
  if (!back || !title || !hero || cards.length < 2) return;

  const customer = cards.find(card => /客户信息/.test(card.textContent || ''));
  const timeline = cards.find(card => /时间节点/.test(card.textContent || ''));
  const claimOrAction = cards.find(card => card !== customer && card !== timeline);
  if (!customer || !timeline || !claimOrAction) return;

  const heading = document.createElement('div');
  heading.className = 'zs-v13-detail-heading';
  back.textContent = '‹ 返回';
  const headingTitle = document.createElement('h1');
  headingTitle.textContent = title.textContent || '客资详情';
  const spacer = document.createElement('span');
  spacer.className = 'zs-v13-detail-spacer';
  spacer.setAttribute('aria-hidden', 'true');
  heading.append(back, headingTitle, spacer);

  customer.classList.add('zs-v13-detail-card');
  timeline.classList.add('zs-v13-timeline-card');
  const needRow = zsFindDetailRow(customer, '需求描述');
  const needCard = document.createElement('section');
  needCard.className = 'zs-v13-need-card';
  const needText = needRow?.querySelector('dd')?.textContent.trim() || '需求待核实';
  needCard.innerHTML = `<h3>客户需求</h3><p></p>`;
  needCard.querySelector('p').textContent = needText;
  needRow?.remove();

  const isClaim = Boolean(claimOrAction.querySelector('#claim-btn'));
  claimOrAction.classList.add(isClaim ? 'zs-v13-claim-card' : 'zs-v13-action-card');

  const wrapper = document.createElement('div');
  wrapper.className = 'zs-v13-detail-page';
  wrapper.append(heading, hero, customer, needCard, claimOrAction, timeline);
  title.remove();
  main.appendChild(wrapper);
  main.dataset.zsV13Detail = '1';
}

const zsLeadDetailObserver = new MutationObserver(zsPatchLeadDetail);
zsLeadDetailObserver.observe(document.documentElement, { childList: true, subtree: true });
window.addEventListener('hashchange', () => queueMicrotask(zsPatchLeadDetail));
zsPatchLeadDetail();
