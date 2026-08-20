const zsPointsIcon = (name, className='zs-svg-icon') => window.ZSIconSystem?.svg(name, className) || '';

function zsPointsRouteActive(){
  return /^#\/points(?:\?|$)/.test(location.hash || '');
}

function zsSyncPointsRouteClass(){
  document.body.classList.toggle('zs-v13-points-route', zsPointsRouteActive());
}

function zsPatchPointsCards(wrapper){
  const cards=[...wrapper.querySelectorAll(':scope > .card')];
  const packageCard=cards.find(card=>/充值档位参考/.test(card.textContent||''));
  const ledgerCard=cards.find(card=>/积分流水/.test(card.textContent||''));
  if(packageCard && packageCard.dataset.zsV13Points!=='1'){
    const items=[...packageCard.querySelectorAll(':scope > .lead-card')];
    if(items.length){
      const grid=document.createElement('div');
      grid.className='zs-v13-package-grid';
      items.forEach(item=>{item.classList.add('zs-v13-package-card');grid.appendChild(item);});
      const help=packageCard.querySelector(':scope > .help');
      packageCard.insertBefore(grid,help||null);
    }
    const heading=packageCard.querySelector('.card-title h3');
    if(heading) heading.textContent='线下充值档位';
    packageCard.dataset.zsV13Points='1';
  }
  if(ledgerCard && ledgerCard.dataset.zsV13Points!=='1'){
    const list=ledgerCard.querySelector('.list');
    list?.classList.add('zs-v13-ledger-list');
    const heading=ledgerCard.querySelector('.card-title h3');
    if(heading) heading.textContent='最近积分流水';
    ledgerCard.dataset.zsV13Points='1';
  }
  const entitlement=wrapper.querySelector(':scope > .p1-entitlements-card');
  if(entitlement) entitlement.dataset.zsV13Points='1';
}

function zsPatchPoints(){
  zsSyncPointsRouteClass();
  if(!zsPointsRouteActive()) return;
  const main=document.querySelector('main.content');
  if(!main) return;
  let wrapper=main.querySelector(':scope > .zs-v13-points-page');
  if(wrapper){zsPatchPointsCards(wrapper);return;}
  const title=main.querySelector(':scope > .page-title');
  const subtitle=main.querySelector(':scope > .subtitle');
  const hero=main.querySelector(':scope > .hero');
  const cards=[...main.querySelectorAll(':scope > .card')];
  if(!title||!subtitle||!hero||cards.length<2) return;

  const heading=document.createElement('div');
  heading.className='zs-v13-points-heading';
  zsSetSafeHtml(heading, `<button type="button" class="zs-icon-label" data-zs-points-home>${zsPointsIcon('chevron-left')}<span>返回</span></button><h1>积分中心</h1><span>积分明细</span>`);
  heading.querySelector('[data-zs-points-home]').onclick=()=>{location.hash='#/home';};

  wrapper=document.createElement('div');
  wrapper.className='zs-v13-points-page';
  wrapper.append(heading,title,subtitle,hero,...cards);
  main.appendChild(wrapper);
  main.dataset.zsV13Points='1';
  zsPatchPointsCards(wrapper);
}

const zsPointsObserver=new MutationObserver(()=>queueMicrotask(zsPatchPoints));
zsPointsObserver.observe(document.documentElement,{childList:true,subtree:true});
window.addEventListener('hashchange',()=>queueMicrotask(zsPatchPoints));
zsPatchPoints();
