const zsNotificationsIcon = (name, className='zs-svg-icon') => window.ZSIconSystem?.svg(name, className) || '';

function zsNotificationsRouteActive(){return /^#\/notifications(?:\?|$)/.test(location.hash||'');}
function zsSyncNotificationsRouteClass(){document.body.classList.toggle('zs-v13-notifications-route',zsNotificationsRouteActive());}
function zsNotificationType(card){
  const text=(card.textContent||'').toLowerCase();
  if(/积分|充值|余额/.test(text)) return 'points';
  if(/退回|审核|驳回/.test(text)) return 'review';
  if(/客资|领取|派发|跟进/.test(text)) return 'leads';
  return 'system';
}
function zsNotificationIcon(type){return {leads:'list',points:'coins',review:'circle-check',system:'bell'}[type]||'bell';}
function zsDecorateNotifications(wrapper){
  const list=wrapper.querySelector(':scope > .list');
  if(!list||list.dataset.zsV13==='1') return;
  list.classList.add('zs-v13-notification-list');
  list.querySelectorAll('[data-notification]').forEach(card=>{
    const type=zsNotificationType(card); card.dataset.zsType=type; card.classList.add('zs-v13-notification-card');
    const icon=document.createElement('div'); icon.className=`zs-v13-notification-icon ${type}`; zsSetSafeHtml(icon, zsNotificationsIcon(zsNotificationIcon(type)));
    const copy=document.createElement('div'); copy.className='zs-v13-notification-copy';
    while(card.firstChild) copy.appendChild(card.firstChild);
    card.append(icon,copy);
  });
  list.dataset.zsV13='1';
}
function zsFilterNotifications(wrapper,type){
  wrapper.querySelectorAll('.zs-v13-notification-tab').forEach(btn=>btn.classList.toggle('active',btn.dataset.type===type));
  wrapper.querySelectorAll('[data-notification]').forEach(card=>{card.hidden=type!=='all'&&card.dataset.zsType!==type;});
}
function zsPatchNotifications(){
  zsSyncNotificationsRouteClass(); if(!zsNotificationsRouteActive()) return;
  const main=document.querySelector('main.content'); if(!main) return;
  let wrapper=main.querySelector(':scope > .zs-v13-notifications-page'); if(wrapper){zsDecorateNotifications(wrapper);return;}
  const title=main.querySelector(':scope > .page-title'); const subtitle=main.querySelector(':scope > .subtitle'); const list=main.querySelector(':scope > .list');
  if(!title||!subtitle||!list) return;
  const unread=list.querySelectorAll('.badge-danger').length;
  const heading=document.createElement('div'); heading.className='zs-v13-notifications-heading';
  zsSetSafeHtml(heading, `<button type="button" class="zs-icon-label" data-zs-message-home>${zsNotificationsIcon('chevron-left')}<span>返回</span></button><h1>消息中心</h1><button type="button" data-zs-read-all>全部已读</button>`);
  heading.querySelector('[data-zs-message-home]').onclick=()=>{location.hash='#/profile';};
  const summary=document.createElement('section'); summary.className='zs-v13-notifications-summary'; zsSetSafeHtml(summary, `<div><span>待处理消息</span><b>${unread} 条未读</b></div><small>客资、积分和审核提醒集中查看</small>`);
  const tabs=document.createElement('div'); tabs.className='zs-v13-notification-tabs';
  [['all','全部'],['leads','客资'],['points','积分'],['review','审核'],['system','系统']].forEach(([type,label])=>{const b=document.createElement('button');b.type='button';b.className='zs-v13-notification-tab'+(type==='all'?' active':'');b.dataset.type=type;b.textContent=label;b.onclick=()=>zsFilterNotifications(wrapper,type);tabs.appendChild(b);});
  wrapper=document.createElement('div'); wrapper.className='zs-v13-notifications-page'; wrapper.append(heading,title,subtitle,summary,tabs,list); main.appendChild(wrapper); main.dataset.zsV13Notifications='1';
  zsDecorateNotifications(wrapper);
  heading.querySelector('[data-zs-read-all]').onclick=async()=>{
    const unreadCards=[...wrapper.querySelectorAll('[data-notification]')].filter(card=>card.querySelector('.badge-danger'));
    try{for(const card of unreadCards){await fetch(`/api/v1/notifications/${encodeURIComponent(card.dataset.notification)}/read`,{method:'POST',credentials:'include'});} location.hash=`#/notifications?refresh=${Date.now()}`;}
    catch{const toast=document.querySelector('#toast');if(toast){toast.textContent='批量标记失败，请稍后重试';toast.className='toast show error';setTimeout(()=>toast.className='toast',2600);}}
  };
}
const zsNotificationsObserver=new MutationObserver(()=>queueMicrotask(zsPatchNotifications));
zsNotificationsObserver.observe(document.documentElement,{childList:true,subtree:true});
window.addEventListener('hashchange',()=>queueMicrotask(zsPatchNotifications));
zsPatchNotifications();
