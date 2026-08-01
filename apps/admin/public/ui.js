const toastEl=document.querySelector('#toast'),modalRoot=document.querySelector('#modal-root');
export const esc=(v='')=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
export const fmt=v=>v?new Date(v).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'--';
export const num=v=>new Intl.NumberFormat('zh-CN').format(Number(v||0));
export const yuan=cents=>`¥${num(Number(cents||0)/100)}`;
export const uuid=()=>crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`;
export function toast(message,type=''){toastEl.textContent=message;toastEl.className=`toast show ${type==='error'?'error':''}`;setTimeout(()=>toastEl.className='toast',2800)}
export function badge(text,type='neutral'){return `<span class="badge badge-${type}">${esc(text)}</span>`}
export function table(headers,rows,empty='暂无数据'){if(!rows.length)return `<div class="empty"><b>⌕</b>${esc(empty)}</div>`;return `<div class="table-wrap"><table class="table"><thead><tr>${headers.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`}
export function openModal(title,body,footer=''){modalRoot.innerHTML=`<div class="modal-bg" id="modal-bg"><section class="modal"><header class="modal-head"><h3>${esc(title)}</h3><button class="btn btn-small btn-outline" data-close>关闭</button></header><div class="modal-body">${body}</div>${footer?`<footer class="modal-footer">${footer}</footer>`:''}</section></div>`;modalRoot.querySelectorAll('[data-close]').forEach(x=>x.onclick=closeOverlay);return modalRoot.querySelector('.modal')}
export function openDrawer(title,body){modalRoot.innerHTML=`<div class="drawer-bg" id="drawer-bg"><aside class="drawer"><header class="drawer-head"><h3>${esc(title)}</h3><button class="btn btn-small btn-outline" data-close>关闭</button></header><div class="drawer-body">${body}</div></aside></div>`;modalRoot.querySelectorAll('[data-close]').forEach(x=>x.onclick=closeOverlay);return modalRoot.querySelector('.drawer')}
export function closeOverlay(){modalRoot.innerHTML=''}
export function field(id,label,input,help=''){return `<div class="field"><label for="${id}">${esc(label)}</label>${input}${help?`<div class="help">${esc(help)}</div>`:''}</div>`}
export function input(id,value='',type='text',placeholder=''){return `<input class="input" id="${id}" type="${type}" value="${esc(value)}" placeholder="${esc(placeholder)}">`}
export function select(id,options,value=''){return `<select class="select" id="${id}">${options.map(([v,l])=>`<option value="${esc(v)}" ${String(v)===String(value)?'selected':''}>${esc(l)}</option>`).join('')}</select>`}
export function pageHead(title,subtitle,actions=''){return `<div class="page-head"><div><h2>${esc(title)}</h2><p>${esc(subtitle)}</p></div><div class="actions">${actions}</div></div>`}
export function statusType(status){return ({ACTIVE:'ok',PUBLISHED:'ok',QUALIFIED:'ok',CLAIMED:'blue',FOLLOWING:'blue',COMPLETED:'ok',SUBMITTED:'ok',APPROVED:'ok',PENDING:'warn',PENDING_CLAIM:'warn',ASSIGNED:'warn',IN_PROGRESS:'blue',RETURN_PENDING:'bad',REJECTED:'bad',INVALID:'bad',IMPORT_ERROR:'bad',DUPLICATE_REVIEW:'warn',FAILED:'bad',DEAD:'bad',DISABLED:'neutral',EXPIRED:'neutral',RELEASED:'neutral'}[status]||'neutral')}
