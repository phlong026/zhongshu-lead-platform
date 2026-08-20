const ADM_PAGE_IDS={
  dashboard:['ADM-02','ADM-03'],staging:['ADM-04'],verification:['ADM-05'],qualified:['ADM-06'],
  assignments:['ADM-08'],companies:['ADM-09'],points:['ADM-11'],recharge:['ADM-12'],ledgers:['ADM-13'],
  returns:['ADM-14'],outbox:['ADM-18'],users:['ADM-17'],configs:['ADM-18'],audit:['ADM-19'],'master-data':['ADM-16']
};
const admIcon=name=>window.ZSIconSystem?.svg(name)||'';
const ADM_META={
  'ADM-01':'管理后台登录',
  'ADM-02':'老板经营看板',
  'ADM-03':'运营工作台',
  'ADM-04':'飞书导入暂存区',
  'ADM-05':'电销核验任务管理',
  'ADM-06':'合格客资池',
  'ADM-07':'人工派发 / 候选公司',
  'ADM-08':'派发订单管理',
  'ADM-09':'加盟商公司列表',
  'ADM-10':'加盟商公司详情',
  'ADM-11':'充值档位 / 等级配置',
  'ADM-12':'线下充值人工入账',
  'ADM-13':'积分账户与流水',
  'ADM-14':'退回审核列表',
  'ADM-15':'退回审核详情',
  'ADM-16':'地区 / 类目 / 品牌配置',
  'ADM-17':'角色权限与字段隔离',
  'ADM-18':'系统规则 / 参数',
  'ADM-19':'操作审计日志'
};
function admRoute(){return (location.hash.replace(/^#\/?/,'').split('?')[0]||'dashboard');}
function admDashboardId(){const labels=[...document.querySelectorAll('main.page .stat .label')].map(node=>node.textContent.trim());return labels.some(label=>/(积分总余额|累计充值|积分收入)/.test(label))?'ADM-02':'ADM-03';}
function admCurrentIds(){const route=admRoute();if(route==='dashboard')return[admDashboardId()];return ADM_PAGE_IDS[route]||[];}
function admAddPageContext(){
  const page=document.querySelector('main.page');const head=page?.querySelector('.page-head');if(!page||!head)return;
  const ids=admCurrentIds();const id=ids[0]||'ADM-03';document.body.dataset.admPage=id;page.dataset.admPageId=ids.join('/');
  if(head.dataset.admV10==='1')return;head.dataset.admV10='1';
  const crumb=document.createElement('div');crumb.className='adm-v10-breadcrumb';zsSetSafeHtml(crumb, `合家美宅 <span>${admIcon('chevron-right')}</span> <b>${ADM_META[id]||'管理后台'}</b>`);page.insertBefore(crumb,head);
}
function admPatchLogin(){const login=document.querySelector('.login-card');if(!login||login.dataset.admV10==='1')return;login.dataset.admV10='1';document.body.dataset.admPage='ADM-01';}
function admPatchTables(){document.querySelectorAll('.table').forEach(t=>{t.setAttribute('role','table');t.querySelectorAll('th').forEach(th=>th.setAttribute('scope','col'));});}
function admPatchRiskActions(){document.querySelectorAll('[data-review="APPROVE"],#do-recharge,[data-disable],[data-publish]').forEach(btn=>{btn.dataset.admRisk='1';btn.title='高风险操作：系统将记录操作者、对象、结果和请求信息';});}
function admPatch(){admPatchLogin();admAddPageContext();admPatchTables();admPatchRiskActions();}
const admObserver=new MutationObserver(()=>queueMicrotask(admPatch));admObserver.observe(document.documentElement,{childList:true,subtree:true});window.addEventListener('hashchange',()=>queueMicrotask(admPatch));admPatch();
