const ZS_STATUS_API='/api/v1';
const ZS_STATUS_NATIVE_FETCH=window.fetch.bind(window);
let zsPendingReturnSuccess=false;
let zsStatusLock=/^#\/(binding-status|return-success)(?:\?|$)/.test(location.hash||'')?location.hash:null;
window.fetch=async function zsStatusFetch(input,init={}){
  const response=await ZS_STATUS_NATIVE_FETCH(input,init);
  const url=typeof input==='string'?input:input.url;
  if(response.ok&&/\/api\/v1\/returns\/[^/]+\/submit(?:\?|$)/.test(url)){
    zsPendingReturnSuccess=true;
    sessionStorage.setItem('zs:return-success',JSON.stringify({id:url.split('/').slice(-2,-1)[0]||'已生成'}));
  }
  return response;
};
const zsStatusEsc=(value='')=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const zsStatusIcon=(name,className='zs-svg-icon')=>window.ZSIconSystem?.svg(name,className)||'';
function zsStatusQuery(){return new URLSearchParams((location.hash.split('?')[1]||''));}
function zsStatusRoute(name){location.hash=`#/${name}`;}
function zsPatchAuthPage(){
  const active=/^#\/(login)?(?:\?|$)/.test(location.hash||'#/login');
  document.body.classList.toggle('zs-v13-auth-route',active);
  if(!active)return;
  const page=document.querySelector('.login-page');
  const panel=page?.querySelector('.login-panel');
  if(!page||!panel||page.dataset.zsStatusV13==='1')return;
  page.dataset.zsStatusV13='1';
  const logo=page.querySelector('.login-logo');
  if(logo){logo.querySelector('h1').textContent='合家美宅';logo.querySelector('p').textContent='加盟商客资助手';}
  const hero=document.createElement('section');hero.className='zs-v13-auth-hero';hero.innerHTML='<h2>欢迎使用加盟商客资平台</h2><p>确认公司信息后完成授权绑定。</p>';
  const inviteCard=document.createElement('section');inviteCard.className='zs-v13-invite-card';inviteCard.hidden=true;inviteCard.innerHTML='<h3>确认加盟商公司</h3><p>正在核验专属邀请…</p>';
  const actions=document.createElement('section');actions.className='zs-v13-login-actions';
  while(panel.firstChild)actions.appendChild(panel.firstChild);
  const agreement=document.createElement('label');agreement.className='zs-v13-agreement';agreement.innerHTML='<input type="checkbox" id="zs-agreement"><span>我已阅读并同意《服务规则》和《隐私政策》</span>';actions.appendChild(agreement);
  panel.appendChild(actions);page.insertBefore(hero,panel);page.insertBefore(inviteCard,panel);
  const foot=document.createElement('p');foot.className='zs-v13-auth-foot';foot.textContent='已绑定微信的负责人可直接登录；新绑定请联系平台获取专属邀请链接。';page.appendChild(foot);
  // P0-04/H3：#wechat-login 的事件绑定已收敛到 app.js 的 bindWechatLogin，
  // 勾选门禁与 confirm-start 跳转统一由该唯一入口承担。
  const invite=zsStatusQuery().get('invite');if(invite)zsLoadInvitePreview(invite,inviteCard);
}
async function zsLoadInvitePreview(invite,card){
  const btn=document.querySelector('#wechat-login');
  // I1：8 秒超时兜底——预览请求不再无限挂起登录门禁。
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),8000);
  try{
    const r=await fetch(`${ZS_STATUS_API}/auth/invites/preview?invite=${encodeURIComponent(invite)}`,{credentials:'include',signal:controller.signal});
    const p=await r.json();
    if(!r.ok||p.code!=='OK'){
      // I2：5xx 视为瞬时故障走可重试；4xx/业务码才是明确拒绝。
      if(!r.ok&&r.status>=500)throw new Error('服务暂时不可用，请稍后重试');
      throw Object.assign(new Error(p.message||'邀请已失效'),{rejected:true});
    }
    const x=p.data;card.hidden=false;zsSetSafeHtml(card, `<h3>请确认是否绑定到【${zsStatusEsc(x.company_name)}】</h3><dl class="zs-v13-invite-grid"><dt>负责人</dt><dd>${zsStatusEsc(x.owner_name||'加盟商负责人')}</dd><dt>服务地区</dt><dd>${zsStatusEsc((x.region_codes||[]).join('、')||'以公司档案为准')}</dd><dt>业务范围</dt><dd>${zsStatusEsc((x.capability_codes||[]).join('、')||'以公司档案为准')}</dd><dt>会员等级</dt><dd>${zsStatusEsc(x.level_code||'V1')}</dd><dt>邀请有效期至</dt><dd>${zsStatusEsc(x.expires_at?new Date(x.expires_at).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'--')}</dd></dl><p class="help">请确认以上公司信息无误，勾选服务规则后点击“微信授权登录”完成绑定。</p>`);
    if(btn){btn.dataset.inviteVerified='1';btn.disabled=false;}
  }catch(e){
    clearTimeout(timer);card.hidden=false;
    // I2：明确的邀请拒绝才锁死按钮；超时/网络异常改为可重试，不判死。
    if(e&&e.rejected){zsSetSafeHtml(card, `<h3>邀请无法使用</h3><p>${zsStatusEsc(e.message)}</p><p class="help">请联系平台重新获取专属邀请链接。</p>`);if(btn){btn.disabled=true;btn.dataset.inviteInvalid='1';}return;}
    const reason=e&&e.name==='AbortError'?'邀请核验超时，请检查网络后重试':(e&&e.message)||'网络异常，请稍后重试';
    zsSetSafeHtml(card, `<h3>邀请核验失败</h3><p>${zsStatusEsc(reason)}</p><button class="btn btn-outline" id="zs-invite-retry">重新核验邀请</button>`);
    const retry=document.querySelector('#zs-invite-retry');if(retry)retry.onclick=()=>{card.hidden=true;zsLoadInvitePreview(invite,card);};
  }finally{clearTimeout(timer);}
}
function zsRenderBindingStatus(){const q=zsStatusQuery(),state=q.get('state')||'pending';const map={pending:['warn','clock','绑定申请审核中','平台正在核对公司与负责人信息，审核完成后即可进入客资页面。'],invalid:['warn','alert-triangle','邀请已失效','请联系平台重新获取专属邀请链接。'],disabled:['warn','alert-triangle','公司暂不可用','该加盟商公司已停用，请联系平台处理。'],bound_other:['warn','alert-triangle','当前微信已绑定其他公司','一个微信仅可绑定一家公司。如需调整，请联系平台客服核实处理。'],oauth_failed:['warn','alert-triangle','微信授权失败','授权未完成，请返回重试；若持续失败请联系平台客服。']};const [kind,icon,title,message]=map[state]||map.pending;zsRenderState({kind,icon,title,message,primary:['刷新状态','binding-status?state=pending'],secondary:['联系平台客服','login']});}
function zsRenderReturnSuccess(){let data={};try{data=JSON.parse(sessionStorage.getItem('zs:return-success')||'{}')}catch{}zsRenderState({kind:'success',icon:'circle-check',title:'退回申请已提交',message:'管理员将核验聊天截图和电话录音。审核通过后，领取时实际扣除的积分将返还。',detail:[['申请编号',data.id||'已生成'],['客资',data.lead||'当前客资'],['申请返还',data.points?`${data.points} 积分`:'以审核结果为准'],['当前状态','待审核']],primary:['查看退回进度','leads?status=RETURN_PENDING'],secondary:['返回我的客资','leads']});}
function zsRenderState({kind='warn',icon='alert-triangle',title,message,detail=[],primary,secondary}){const app=document.querySelector('#app');if(!app)return;document.body.classList.remove('zs-v13-auth-route');zsSetSafeHtml(app, `<main class="zs-v13-state-page"><div class="zs-v13-state-brand"><img src="./logo.png" alt="合家美宅"><span>合家美宅</span></div><section class="zs-v13-state-card"><div class="zs-v13-state-icon ${kind}">${zsStatusIcon(icon)}</div><h1>${zsStatusEsc(title)}</h1><p>${zsStatusEsc(message)}</p>${detail.length?`<div class="zs-v13-state-detail">${detail.map(([a,b])=>`<div><span>${zsStatusEsc(a)}</span><b>${zsStatusEsc(b)}</b></div>`).join('')}</div>`:''}</section><div class="zs-v13-state-actions">${primary?`<button class="btn btn-primary" data-zs-status-route="${zsStatusEsc(primary[1])}">${zsStatusEsc(primary[0])}</button>`:''}${secondary?`<button class="btn btn-outline" data-zs-status-route="${zsStatusEsc(secondary[1])}">${zsStatusEsc(secondary[0])}</button>`:''}</div></main>`);}
function zsPatchLinkLanding(){const active=/^#\/link\//.test(location.hash||'');document.body.classList.toggle('zs-v13-link-loading',active);if(!active)return;const main=document.querySelector('main.content');if(!main||main.querySelector('.zs-v13-link-landing'))return;zsSetSafeHtml(main, `<section class="zs-v13-link-landing"><i>${zsStatusIcon('external-link')}</i><h2>正在进入客资详情</h2><p>系统正在校验微信身份、加盟商公司、订单状态和深链签名。</p><div class="zs-v13-loading-dots"><b></b><b></b><b></b></div></section>`);}
function zsPatchInvalidLink(){const empty=document.querySelector('main.content .empty');if(!empty||!/(链接已失效|已被回收|页面加载失败)/.test(empty.textContent||''))return false;if(empty.dataset.zsSecure==='1')return true;empty.dataset.zsSecure='1';zsSetSafeHtml(empty, `<div class="zs-v13-state-icon">${zsStatusIcon('link-off')}</div><h2>该链接已失效</h2><p>客资可能已被领取、回收、释放，或当前账号无权访问。为保护客户隐私，本页面不展示任何客资摘要。</p><button class="btn btn-primary" data-zs-status-route="leads">返回客资列表</button>`);document.body.classList.remove('zs-v13-link-loading');return true;
}
function zsStatusPatch(){zsPatchAuthPage();if(zsPatchInvalidLink())return;zsPatchLinkLanding();}
window.zsRenderBindingStatus=zsRenderBindingStatus;window.zsRenderReturnSuccess=zsRenderReturnSuccess;
const zsStatusObserver=new MutationObserver(zsStatusPatch);zsStatusObserver.observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('click',e=>{const b=e.target.closest('[data-zs-status-route]');if(!b)return;e.preventDefault();zsStatusRoute(b.dataset.zsStatusRoute);});
window.addEventListener('hashchange',event=>{
  const hash=location.hash||'';
  if(zsPendingReturnSuccess&&/^#\/leads(?:\?|$)/.test(hash)){
    zsPendingReturnSuccess=false;zsStatusLock='#/return-success';event.stopImmediatePropagation();location.hash=zsStatusLock;return;
  }
  if(zsStatusLock&&hash==='#/home'){event.stopImmediatePropagation();location.hash=zsStatusLock;return;}
  if(/^#\/binding-status(?:\?|$)/.test(hash)){zsStatusLock=hash;event.stopImmediatePropagation();zsRenderBindingStatus();return;}
  if(/^#\/return-success(?:\?|$)/.test(hash)){zsStatusLock=hash;event.stopImmediatePropagation();zsRenderReturnSuccess();return;}
  zsStatusLock=null;queueMicrotask(zsStatusPatch);
},true);
if(/^#\/binding-status(?:\?|$)/.test(location.hash||''))zsRenderBindingStatus();
else if(/^#\/return-success(?:\?|$)/.test(location.hash||''))zsRenderReturnSuccess();
else zsStatusPatch();
