function zsProfileRouteActive(){return /^#\/profile(?:\?|$)/.test(location.hash||'');}
function zsSyncProfileRouteClass(){document.body.classList.toggle('zs-v13-profile-route',zsProfileRouteActive());}
function zsProfileIcon(name){return window.ZSIconSystem?.svg(name)||'';}
function zsPatchProfileActionIcons(actions){
  const icons=[[actions.querySelector('[data-route="notifications"]'),'bell'],[actions.querySelector('[data-route="points"]'),'coins'],[actions.querySelector('#logout'),'log-out']];
  for(const [button,name] of icons){if(!button||button.querySelector('.zs-v13-profile-action-icon'))continue;const icon=document.createElement('span');icon.className='zs-v13-profile-action-icon';zsSetSafeHtml(icon,zsProfileIcon(name));button.prepend(icon);}
}
async function zsProfileJson(path){const r=await fetch(`/api/v1${path}`,{credentials:'include'});const p=await r.json().catch(()=>({}));if(!r.ok||p.code!=='OK')throw new Error(p.message||'请求失败');return p.data;}
function zsMetric(label,value){const item=document.createElement('div');item.className='zs-v13-profile-metric';const span=document.createElement('span');span.textContent=label;const b=document.createElement('b');b.textContent=Number(value||0).toLocaleString('zh-CN');item.append(span,b);return item;}
async function zsLoadProfileMetrics(card){
  if(card.querySelector('.zs-v13-profile-metrics'))return;
  try{
    const me=await zsProfileJson('/auth/me');
    const [account,ledgers]=await Promise.all([zsProfileJson(`/points/accounts/${encodeURIComponent(me.company_id)}`),zsProfileJson(`/points/ledgers?company_id=${encodeURIComponent(me.company_id)}&page=1&page_size=200`)]);
    const rows=ledgers.items||[];
    const consumed=rows.filter(x=>x.type==='CLAIM'&&x.delta<0).reduce((sum,x)=>sum+Math.abs(Number(x.delta||0)),0);
    const returned=rows.filter(x=>x.type==='RETURN'&&x.delta>0).reduce((sum,x)=>sum+Number(x.delta||0),0);
    const metrics=document.createElement('div');metrics.className='zs-v13-profile-metrics';metrics.append(zsMetric('当前积分',account.balance),zsMetric('累计消耗',consumed),zsMetric('退回积分',returned));card.appendChild(metrics);
    const brand=card.querySelector(':scope > .brand');if(brand&&!brand.querySelector('.zs-v13-profile-level')){const level=document.createElement('span');level.className='zs-v13-profile-level';level.textContent=`${account.level_code||'V1'} 战略`;brand.appendChild(level);}
  }catch{/* 主页面统一处理鉴权；统计增强失败不阻断。 */}
}
function zsPatchProfile(){
  zsSyncProfileRouteClass();if(!zsProfileRouteActive())return;
  const main=document.querySelector('main.content');if(!main)return;
  let wrapper=main.querySelector(':scope > .zs-v13-profile-page');if(wrapper){const card=wrapper.querySelector('.zs-v13-company-card');if(card)zsLoadProfileMetrics(card);return;}
  const title=main.querySelector(':scope > .page-title');const cards=[...main.querySelectorAll(':scope > .card')];if(!title||cards.length<3)return;
  const company=cards[0],actions=cards.find(c=>c.querySelector('#logout')),security=cards.find(c=>/隐私与安全/.test(c.textContent||''));if(!actions||!security)return;
  const heading=document.createElement('div');heading.className='zs-v13-profile-heading';heading.innerHTML='<h1>我的</h1>';
  company.classList.add('zs-v13-company-card');actions.classList.add('zs-v13-profile-actions');zsPatchProfileActionIcons(actions);security.classList.add('zs-v13-security-card');
  wrapper=document.createElement('div');wrapper.className='zs-v13-profile-page';wrapper.append(heading,title,company,actions,security);main.appendChild(wrapper);main.dataset.zsV13Profile='1';zsLoadProfileMetrics(company);
}
const zsProfileObserver=new MutationObserver(()=>queueMicrotask(zsPatchProfile));zsProfileObserver.observe(document.documentElement,{childList:true,subtree:true});window.addEventListener('hashchange',()=>queueMicrotask(zsPatchProfile));zsPatchProfile();
