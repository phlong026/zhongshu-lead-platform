const toastEl=document.querySelector('#toast'),modalRoot=document.querySelector('#modal-root');
export const esc=(v='')=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
export const fmt=v=>v?new Date(v).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'--';
export const num=v=>new Intl.NumberFormat('zh-CN').format(Number(v||0));
export const yuan=cents=>`¥${num(Number(cents||0)/100)}`;
export const uuid=()=>crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`;
export const icon=name=>window.ZSIconSystem?.svg(name)||'';
const STATUS_LABELS={
  ACTIVE:'正常',DISABLED:'已停用',PUBLISHED:'已发布',QUALIFIED:'已通过核验',
  DRAFT:'待完善',IMPORTED:'待补信息',IMPORT_ERROR:'导入异常',DUPLICATE_REVIEW:'疑似重复',
  PENDING:'待处理',PENDING_REVIEW:'待初审',READY_DISPATCH:'待派发',PENDING_CLAIM:'待领取',
  ASSIGNED:'待处理',CLAIMED:'已领取',FOLLOWING:'跟进中',IN_PROGRESS:'处理中',SUBMITTED:'已提交',
  VERIFYING:'核验中',REVIEWING:'待终审',NEED_MORE_EVIDENCE:'待补充材料',
  APPROVED:'已通过',REJECTED:'已驳回',INVALID:'需要修改',COMPLETED:'已完成',
  RETURN_PENDING:'退回审核中',RETURNED:'已退回',RELEASED:'已释放',EXPIRED:'已过期',
  FAILED:'发送失败',DEAD:'需人工处理',MANUAL_ACTION_REQUIRED:'需人工处理',
  CLEAR:'未发现重复',DUPLICATE:'疑似重复',OBSERVING:'确认中',FROZEN:'暂缓结算',
  SETTLED:'已结算',CANCELLED:'已取消',REVERSED:'已调整',
  OLD_RENOVATION:'旧房改造',SELF_BUILD:'农村自建房',INTERIOR:'室内装修',
  ZHONGSHU:'合家美宅',PARTNER:'合作品牌',V1:'普通加盟商',V2:'重点加盟商',V3:'核心加盟商'
};
const TECHNICAL_CODE=/^(?:[A-Z][A-Z0-9_]{2,}|[a-z][a-z0-9]*|[a-z0-9]+(?:[_-][a-z0-9]+)+)$/;
export function readableLabel(value,fallback='待确认'){if(Array.isArray(value))return value.map(item=>readableLabel(item,fallback)).filter(Boolean).join('、')||fallback;if(value&&typeof value==='object')return fallback;const text=String(value??'').trim();if(!text)return fallback;return STATUS_LABELS[text]||(TECHNICAL_CODE.test(text)?fallback:text)}
export function recordCode(value,prefix='记录'){const text=String(value??'').replace(/-/g,'');if(!text)return'--';return `${prefix}-${text.slice(-8).toUpperCase()}`}
export function toast(message,type=''){toastEl.textContent=message;toastEl.className=`toast show ${type==='error'?'error':''}`;setTimeout(()=>toastEl.className='toast',2800)}
export function badge(text,type='neutral'){return `<span class="badge badge-${type}">${esc(readableLabel(text))}</span>`}
export function table(headers,rows,empty='暂无数据'){if(!rows.length)return `<div class="empty"><b>${icon('search')}</b>${esc(empty)}</div>`;return `<div class="table-wrap"><table class="table"><thead><tr>${headers.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`}
export function openModal(title,body,footer=''){zsSetSafeHtml(modalRoot, `<div class="modal-bg" id="modal-bg"><section class="modal"><header class="modal-head"><h3>${esc(title)}</h3><button class="btn btn-small btn-outline" data-close>关闭</button></header><div class="modal-body">${body}</div>${footer?`<footer class="modal-footer">${footer}</footer>`:''}</section></div>`);modalRoot.querySelectorAll('[data-close]').forEach(x=>x.onclick=closeOverlay);return modalRoot.querySelector('.modal')}
export function openDrawer(title,body){zsSetSafeHtml(modalRoot, `<div class="drawer-bg" id="drawer-bg"><aside class="drawer"><header class="drawer-head"><h3>${esc(title)}</h3><button class="btn btn-small btn-outline" data-close>关闭</button></header><div class="drawer-body">${body}</div></aside></div>`);modalRoot.querySelectorAll('[data-close]').forEach(x=>x.onclick=closeOverlay);return modalRoot.querySelector('.drawer')}
export function closeOverlay(){modalRoot.innerHTML=''}
export function field(id,label,input,help=''){return `<div class="field"><label for="${id}">${esc(label)}</label>${input}${help?`<div class="help">${esc(help)}</div>`:''}</div>`}
export function input(id,value='',type='text',placeholder=''){return `<input class="input" id="${id}" type="${type}" value="${esc(value)}" placeholder="${esc(placeholder)}">`}
export function select(id,options,value=''){return `<select class="select" id="${id}">${options.map(([v,l])=>`<option value="${esc(v)}" ${String(v)===String(value)?'selected':''}>${esc(l)}</option>`).join('')}</select>`}
export function pageHead(title,subtitle,actions=''){return `<div class="page-head"><div><h2>${esc(title)}</h2><p>${esc(subtitle)}</p></div><div class="actions">${actions}</div></div>`}
export function statusType(status){return ({ACTIVE:'ok',PUBLISHED:'ok',QUALIFIED:'ok',CLAIMED:'blue',FOLLOWING:'blue',COMPLETED:'ok',SUBMITTED:'ok',APPROVED:'ok',PENDING:'warn',PENDING_CLAIM:'warn',ASSIGNED:'warn',IN_PROGRESS:'blue',RETURN_PENDING:'bad',REJECTED:'bad',INVALID:'bad',IMPORT_ERROR:'bad',DUPLICATE_REVIEW:'warn',FAILED:'bad',DEAD:'bad',DISABLED:'neutral',EXPIRED:'neutral',RELEASED:'neutral'}[status]||'neutral')}
