const API='/api/v1';
let permissions=[];
let checking=false;
let lastCheckedAt=0;

async function refreshPermissions(){
  const now=Date.now();
  if(checking||now-lastCheckedAt<3000)return;
  checking=true;lastCheckedAt=now;
  try{
    const response=await fetch(`${API}/auth/me`,{credentials:'include'});
    const payload=await response.json();
    permissions=response.ok&&payload.code==='OK'?(payload.data.permissions||[]):[];
  }catch{permissions=[]}finally{checking=false;injectEntry()}
}
function allowed(){
  return permissions.includes('*')||[
    'assignment.own.read','supplier.lead.manage','supplier.reward.own.read',
    'return.own.manage','notification.own.read'
  ].some(code=>permissions.includes(code));
}
function openWorkbench(){location.href='./v12-workbench.html'}
function injectEntry(){
  if(!allowed()){refreshPermissions();return}
  const topbar=document.querySelector('.topbar');
  if(topbar&&!document.querySelector('#v12-workbench-top')){
    const button=document.createElement('button');
    button.className='icon-btn';button.id='v12-workbench-top';button.type='button';
    button.setAttribute('aria-label','V1.2 全链路工作台');button.textContent='链';
    button.onclick=openWorkbench;
    const notice=topbar.querySelector('[data-route="notifications"]');
    topbar.insertBefore(button,notice||null);
  }
  if(location.hash.startsWith('#/profile')&&!document.querySelector('#v12-workbench-profile')){
    const cards=[...document.querySelectorAll('.content .card')];
    const target=cards.find(card=>card.querySelector('#logout'))||cards[0];
    if(target){
      const button=document.createElement('button');
      button.className='btn btn-primary btn-block';button.id='v12-workbench-profile';button.type='button';
      button.style.marginBottom='10px';button.textContent='进入 V1.2 全链路工作台';button.onclick=openWorkbench;
      target.prepend(button);
    }
  }
}
const observer=new MutationObserver(injectEntry);
observer.observe(document.body,{childList:true,subtree:true});
refreshPermissions();
