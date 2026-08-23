const API='/api/v1';
const workbenchEntryIcon=(name,className='zs-svg-icon')=>window.ZSIconSystem?.svg(name,className)||'';
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
    'points.own.read','return.own.manage','notification.own.read',
    'company.profile.manage'
  ].some(code=>permissions.includes(code));
}
function openWorkbench(){location.href='./v12-workbench.html'}
function injectEntry(){
  if(!allowed()){refreshPermissions();return}
  if(location.hash.startsWith('#/profile')&&!document.querySelector('#v12-workbench-profile')){
    const cards=[...document.querySelectorAll('.content .card')];
    const target=cards.find(card=>card.querySelector('#logout'))||cards[0];
    if(target){
      const button=document.createElement('button');
      button.className='btn btn-primary btn-block';button.id='v12-workbench-profile';button.type='button';
      zsSetSafeHtml(button,`<span class="zs-v13-profile-action-icon">${workbenchEntryIcon('home')}</span><span>进入客资工作台</span>`);button.onclick=openWorkbench;
      target.prepend(button);
    }
  }
}
const observer=new MutationObserver(injectEntry);
observer.observe(document.body,{childList:true,subtree:true});
refreshPermissions();
