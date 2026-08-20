const ZS_FOLLOW_LABELS={CONTACTED:'已联系',INTERESTED:'意向客户',NOT_INTERESTED:'无意向',DEAL:'已成交',INVALID:'无效'};
const zsFollowupIcon=(name,className='zs-svg-icon')=>window.ZSIconSystem?.svg(name,className)||'';
function zsPatchFollowupModal(){
  const modal=document.querySelector('#follow-modal .modal');if(!modal||modal.dataset.zsV13==='1')return;
  const title=modal.querySelector('h2');const select=modal.querySelector('#follow-status');const note=modal.querySelector('#follow-note');const save=modal.querySelector('#save-follow');const cancel=modal.querySelector('#cancel-follow');
  if(!title||!select||!note||!save||!cancel)return;
  const subtitle=document.createElement('p');subtitle.className='zs-v13-follow-subtitle';subtitle.textContent='记录真实沟通结果，帮助后续转化';title.after(subtitle);
  const chips=document.createElement('div');chips.className='zs-v13-follow-chips';
  [...select.options].forEach(option=>{const btn=document.createElement('button');btn.type='button';btn.className='zs-v13-follow-chip'+(option.value===select.value?' active':'');btn.dataset.value=option.value;btn.textContent=ZS_FOLLOW_LABELS[option.value]||option.textContent;btn.onclick=()=>{select.value=option.value;chips.querySelectorAll('.zs-v13-follow-chip').forEach(x=>x.classList.toggle('active',x===btn));};chips.appendChild(btn);});
  select.after(chips);
  note.maxLength=200;const count=document.createElement('div');count.className='zs-v13-follow-count';const sync=()=>count.textContent=`${note.value.length} / 200`;note.after(count);note.addEventListener('input',sync);sync();
  const tip=document.createElement('div');tip.className='zs-v13-follow-tip';zsSetSafeHtml(tip, `<b>${zsFollowupIcon('alert-triangle')}</b><span>提交后会记录跟进时间和操作人，历史记录不可删除。</span>`);
  const actions=document.createElement('div');actions.className='zs-v13-follow-actions';actions.append(cancel,save);modal.append(tip,actions);modal.dataset.zsV13='1';
}
const zsFollowObserver=new MutationObserver(()=>queueMicrotask(zsPatchFollowupModal));zsFollowObserver.observe(document.documentElement,{childList:true,subtree:true});zsPatchFollowupModal();
