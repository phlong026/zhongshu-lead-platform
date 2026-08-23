const API='/api/v1';
const supplierEntryIcon=(name,className='zs-svg-icon')=>window.ZSIconSystem?.svg(name,className)||'';
let permissions=[];
let checking=false;
let lastCheckedAt=0;

async function refreshPermissions(){
  const now=Date.now();if(checking||now-lastCheckedAt<3000)return;
  checking=true;lastCheckedAt=now;
  try{
    const response=await fetch(`${API}/auth/me`,{credentials:'include'});
    const payload=await response.json();
    permissions=response.ok&&payload.code==='OK'?(payload.data.permissions||[]):[];
  }catch{permissions=[];}finally{checking=false;injectEntry();}
}
function allowed(){return permissions.includes('*')||permissions.includes('supplier.lead.manage');}
function injectEntry(){
  if(!allowed()){refreshPermissions();return;}
  const topbar=document.querySelector('.topbar');
  if(topbar&&!document.querySelector('#supplier-workspace-top')){
    const button=document.createElement('button');button.className='icon-btn';button.id='supplier-workspace-top';button.type='button';button.setAttribute('aria-label','加盟商客资');zsSetSafeHtml(button,supplierEntryIcon('plus'));button.onclick=()=>{location.href='./supplier.html';};
    const notice=topbar.querySelector('[data-route="notifications"]');topbar.insertBefore(button,notice||null);
  }
  if(location.hash.startsWith('#/profile')&&!document.querySelector('#supplier-workspace-profile')){
    const cards=[...document.querySelectorAll('.content .card')];const target=cards.find(card=>card.querySelector('#logout'))||cards[0];
    if(target){const button=document.createElement('button');button.className='btn btn-primary btn-block';button.id='supplier-workspace-profile';button.type='button';button.style.marginBottom='10px';button.textContent='加盟商客资上传';button.onclick=()=>{location.href='./supplier.html';};target.prepend(button);}
  }
}
const observer=new MutationObserver(injectEntry);observer.observe(document.body,{childList:true,subtree:true});refreshPermissions();
