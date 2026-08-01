const ADM_PAGE_IDS={
  dashboard:['ADM-02','ADM-03'],staging:['ADM-04'],verification:['ADM-05'],qualified:['ADM-06'],
  assignments:['ADM-08'],companies:['ADM-09'],points:['ADM-11'],recharge:['ADM-12'],ledgers:['ADM-13'],
  returns:['ADM-14'],outbox:['ADM-18'],users:['ADM-17'],configs:['ADM-18'],audit:['ADM-19'],'master-data':['ADM-16']
};
const ADM_META={
  'ADM-01':['管理后台登录','内部账号、会话与角色权限入口','secure'],
  'ADM-02':['老板经营看板','业务与财务汇总仅按授权展示','secure'],
  'ADM-03':['运营工作台','客资、核验、派发和异常；不展示财务字段','secure'],
  'ADM-04':['飞书导入暂存区','导入、异常、疑似重复和字段修正','normal'],
  'ADM-05':['电销核验任务管理','任务分配、回收、进度与模板','normal'],
  'ADM-06':['合格客资池','筛选、查看与人工派发入口','normal'],
  'ADM-07':['人工派发 / 候选公司','仅展示资格状态，不展示具体积分余额','secure'],
  'ADM-08':['派发订单管理','待领取、已领取、回收与轨迹','normal'],
  'ADM-09':['加盟商公司列表','状态、地区、类目与微信绑定','normal'],
  'ADM-10':['加盟商公司详情','资料、服务范围、邀请与主账号','risk'],
  'ADM-11':['充值档位 / 等级配置','金额、基础分、赠分、等级和版本','risk'],
  'ADM-12':['线下充值人工入账','现金在线下完成，后台仅记录并增加积分','risk'],
  'ADM-13':['积分账户与流水','充值、扣减、返还和冲正均不可变留痕','risk'],
  'ADM-14':['退回审核列表','待审、补充、通过与驳回','secure'],
  'ADM-15':['退回审核详情','截图、录音、积分影响与审批','risk'],
  'ADM-16':['地区 / 类目 / 品牌配置','字典、停用与历史版本','normal'],
  'ADM-17':['角色权限与字段隔离','菜单、接口、字段和数据范围同步生效','risk'],
  'ADM-18':['系统规则 / 参数','24/48 小时、阈值、文件限制和开关','risk'],
  'ADM-19':['操作审计日志','高风险操作、查询和导出','secure']
};
function admRoute(){return (location.hash.replace(/^#\/?/,'').split('?')[0]||'dashboard');}
function admDashboardId(){const labels=[...document.querySelectorAll('main.page .stat .label')].map(node=>node.textContent.trim());return labels.some(label=>/(积分总余额|累计充值|积分收入)/.test(label))?'ADM-02':'ADM-03';}
function admCurrentIds(){const route=admRoute();if(route==='dashboard')return[admDashboardId()];return ADM_PAGE_IDS[route]||[];}
function admAddPageContext(){
  const page=document.querySelector('main.page');const head=page?.querySelector('.page-head');if(!page||!head)return;
  const ids=admCurrentIds();const id=ids[0]||'ADM-03';document.body.dataset.admPage=id;page.dataset.admPageId=ids.join('/');
  if(head.dataset.admV10==='1')return;head.dataset.admV10='1';
  const heading=head.querySelector('h2');if(heading){const row=document.createElement('div');row.className='adm-v10-page-title';heading.parentNode.insertBefore(row,heading);row.appendChild(heading);ids.forEach(code=>{const tag=document.createElement('span');tag.className='adm-v10-page-id';tag.textContent=code;row.appendChild(tag);});}
  const crumb=document.createElement('div');crumb.className='adm-v10-breadcrumb';crumb.innerHTML=`众墅之家 <span>›</span> <b>${ADM_META[id]?.[0]||'管理后台'}</b>`;page.insertBefore(crumb,head);
  const meta=ADM_META[id]||['管理后台','基于当前角色和权限显示数据','normal'];const scope=document.createElement('div');scope.className=`adm-v10-scope ${meta[2]==='risk'?'risk':meta[2]==='secure'?'secure':''}`;scope.innerHTML=`<i>${meta[2]==='risk'?'!':'✓'}</i><span>${meta[1]}。页面、接口、数据范围和字段权限必须同时生效。</span>`;head.insertAdjacentElement('afterend',scope);
}
function admPatchLogin(){const login=document.querySelector('.login-card');if(!login||login.dataset.admV10==='1')return;login.dataset.admV10='1';document.body.dataset.admPage='ADM-01';const tag=document.createElement('div');tag.className='adm-v10-page-id adm-v10-login-id';tag.textContent='ADM-01';login.insertBefore(tag,login.firstChild);const note=document.createElement('div');note.className='adm-v10-login-security';note.textContent='登录后根据角色控制菜单、接口、数据范围和财务字段；生产环境预留验证码与二次验证。';login.appendChild(note);}
function admOverlayId(title){if(/人工派发/.test(title))return'ADM-07';if(/加盟商|邀请|公司详情/.test(title))return'ADM-10';if(/退回审核详情/.test(title))return'ADM-15';if(/充值|积分调整|冲正/.test(title))return'ADM-12';return'';}
function admPatchOverlays(){
  document.querySelectorAll('.drawer,.modal').forEach(overlay=>{if(overlay.dataset.admV10==='1')return;const title=overlay.querySelector('.drawer-head,.modal-head')?.textContent?.trim()||'';const id=admOverlayId(title);if(!id)return;overlay.dataset.admV10='1';overlay.dataset.admPageId=id;const h=overlay.querySelector('.drawer-head,.modal-head');if(h){const tag=document.createElement('span');tag.className='adm-v10-overlay-id';tag.textContent=id;h.querySelector('h2,h3')?.appendChild(tag);}if(id==='ADM-15'){const note=document.createElement('div');note.className='adm-v10-evidence-note';note.textContent='证据采用私有存储与短时授权访问；审核通过后仅返还领取时实际扣除积分，且只能执行一次。';overlay.querySelector('.drawer-body,.modal-body')?.prepend(note);}});
}
function admPatchTables(){document.querySelectorAll('.table').forEach(t=>{t.setAttribute('role','table');t.querySelectorAll('th').forEach(th=>th.setAttribute('scope','col'));});}
function admPatchRiskActions(){document.querySelectorAll('[data-review="APPROVE"],#do-recharge,[data-disable],[data-publish]').forEach(btn=>{btn.dataset.admRisk='1';btn.title='高风险操作：系统将记录操作者、对象、结果和请求信息';});}
function admPatch(){admPatchLogin();admAddPageContext();admPatchOverlays();admPatchTables();admPatchRiskActions();}
const admObserver=new MutationObserver(()=>queueMicrotask(admPatch));admObserver.observe(document.documentElement,{childList:true,subtree:true});window.addEventListener('hashchange',()=>queueMicrotask(admPatch));admPatch();
