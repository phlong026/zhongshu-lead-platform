import {request} from './api.js';

let checking=false;
let lastCheckedAt=0;
let permissions=[];

async function refreshPermissions(){
  const now=Date.now();
  if(checking||now-lastCheckedAt<3000)return;
  checking=true;lastCheckedAt=now;
  try{const me=await request('/auth/me');permissions=me.permissions||[];}catch{permissions=[];}finally{checking=false;injectEntries();}
}
function can(code){return permissions.includes('*')||permissions.includes(code);}
function canLeadEntry(){return can('lead.manual.manage')||can('lead.supplier.review');}
function canOperations(){return ['lead.dispatch','return.read','return.review','verification.read','reward.read','reward.manage','reward.reverse','report.v12.read','audit.read'].some(can);}
function makeLink(id,href,icon,label){const link=document.createElement('a');link.className='menu-item';link.id=id;link.href=href;zsSetSafeHtml(link, `<i>${icon}</i>${label}`);return link;}
function injectEntries(){
  const sidebar=document.querySelector('#sidebar');
  if(!sidebar){refreshPermissions();return;}
  if((canLeadEntry()||canOperations())&&!document.querySelector('#v12-platform-label')){
    const label=document.createElement('div');label.className='menu-label';label.id='v12-platform-label';label.textContent='V1.2 客资全链路';sidebar.append(label);
  }
  if(canLeadEntry()&&!document.querySelector('#v12-lead-supply-entry'))sidebar.append(makeLink('v12-lead-supply-entry','./v12-leads.html','＋','客资录入与初审'));
  if(canOperations()&&!document.querySelector('#v12-operations-entry'))sidebar.append(makeLink('v12-operations-entry','./v12-operations.html','▦','全链路运营台'));
}
const observer=new MutationObserver(injectEntries);
observer.observe(document.body,{childList:true,subtree:true});
refreshPermissions();
