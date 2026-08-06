import {request} from './api.js';

let checking=false;
let lastCheckedAt=0;
let permissions=[];

async function refreshPermissions(){
  const now=Date.now();
  if(checking||now-lastCheckedAt<3000)return;
  checking=true;lastCheckedAt=now;
  try{const me=await request('/auth/me');permissions=me.permissions||[];}catch{permissions=[];}finally{checking=false;injectEntry();}
}
function allowed(){return permissions.includes('*')||permissions.includes('lead.manual.manage')||permissions.includes('lead.supplier.review');}
function injectEntry(){
  const sidebar=document.querySelector('#sidebar');
  if(!sidebar||document.querySelector('#v12-lead-supply-entry'))return;
  if(!allowed()){refreshPermissions();return;}
  const label=document.createElement('div');label.className='menu-label';label.id='v12-lead-supply-label';label.textContent='V1.2 客资供给';
  const link=document.createElement('a');link.className='menu-item';link.id='v12-lead-supply-entry';link.href='./v12-leads.html';link.innerHTML='<i>＋</i>客资录入与初审';
  sidebar.append(label,link);
}
const observer=new MutationObserver(injectEntry);
observer.observe(document.body,{childList:true,subtree:true});
refreshPermissions();
