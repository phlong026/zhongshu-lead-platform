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
  if(location.hash.startsWith('#/profile')&&!document.querySelector('#supplier-workspace-profile')){
    const cards=[...document.querySelectorAll('.content .card')];const target=cards.find(card=>card.querySelector('#logout'))||cards[0];
    if(target){const button=document.createElement('button');button.className='btn btn-primary btn-block';button.id='supplier-workspace-profile';button.type='button';zsSetSafeHtml(button,`<span class="zs-v13-profile-action-icon">${supplierEntryIcon('plus')}</span><span>上传客资</span>`);button.onclick=()=>{location.href='./supplier.html';};target.prepend(button);}
  }
}
const observer=new MutationObserver(injectEntry);observer.observe(document.body,{childList:true,subtree:true});refreshPermissions();
