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
  const hero=document.createElement('section');hero.className='zs-v13-auth-hero';hero.innerHTML='<h2>欢迎使用加盟商客资平台</h2><p>授权后进入客资页面。</p>';
  const inviteCard=document.createElement('section');inviteCard.className='zs-v13-invite-card';inviteCard.hidden=true;inviteCard.innerHTML='<h3>确认加盟商公司</h3><p>正在核验专属邀请…</p>';
  const actions=document.createElement('section');actions.className='zs-v13-login-actions';
  while(panel.firstChild)actions.appendChild(panel.firstChild);
  const agreement=document.createElement('label');agreement.className='zs-v13-agreement';agreement.innerHTML='<input type="checkbox" id="zs-agreement"><span>我已阅读并同意《服务规则》和《隐私政策》</span>';actions.appendChild(agreement);
  panel.appendChild(actions);page.insertBefore(hero,panel);page.insertBefore(inviteCard,panel);
  const foot=document.createElement('p');foot.className='zs-v13-auth-foot';foot.textContent='请通过公众号菜单或专属邀请链接进入。';page.appendChild(foot);
  const button=document.querySelector('#wechat-login');if(button){const original=button.onclick;button.onclick=(event)=>{if(!document.querySelector('#zs-agreement')?.checked){event?.preventDefault();const t=document.querySelector('#toast');if(t){t.textContent='请先阅读并同意服务规则和隐私政策';t.className='toast show error';setTimeout(()=>t.className='toast',2600);}return;}original?.call(button,event);};}
  const invite=zsStatusQuery().get('invite');if(invite)zsLoadInvitePreview(invite,inviteCard);
}
async function zsLoadInvitePreview(invite,card){
  try{const r=await fetch(`${ZS_STATUS_API}/auth/invites/preview?invite=${encodeURIComponent(invite)}`,{credentials:'include'});const p=await r.json();if(!r.ok||p.code!=='OK')throw new Error(p.message||'邀请已失效');const x=p.data;card.hidden=false;zsSetSafeHtml(card, `<h3>${zsStatusEsc(x.company_name)}</h3><dl class="zs-v13-invite-grid"><dt>负责人</dt><dd>${zsStatusEsc(x.owner_name||'加盟商负责人')}</dd><dt>服务地区</dt><dd>${zsStatusEsc((x.region_codes||[]).join('、')||'以公司档案为准')}</dd><dt>业务范围</dt><dd>${zsStatusEsc((x.capability_codes||[]).join('、')||'以公司档案为准')}</dd><dt>会员等级</dt><dd>${zsStatusEsc(x.level_code||'V1')}</dd></dl>`);
  }catch(e){card.hidden=false;zsSetSafeHtml(card, `<h3>邀请无法使用</h3><p>${zsStatusEsc(e.message)}</p>`);const btn=document.querySelector('#wechat-login');if(btn)btn.disabled=true;}
}
function zsRenderBindingStatus(){const q=zsStatusQuery(),state=q.get('state')||'pending';const map={pending:['warn','◷','绑定申请审核中','平台正在核对公司与负责人信息，审核完成后即可进入客资页面。'],invalid:['warn','!','邀请已失效','请联系平台重新获取专属邀请链接。'],disabled:['warn','!','公司暂不可用','该加盟商公司已停用，请联系平台处理。'],bound_other:['warn','!','当前微信已绑定其他公司','系统禁止自动覆盖，请联系平台管理员执行换绑并留痕。'],oauth_failed:['warn','!','微信授权失败','授权未完成，请从原邀请链接重新进入。']};const [kind,icon,title,message]=map[state]||map.pending;zsRenderState({kind,icon,title,message,primary:['刷新状态','binding-status?state=pending'],secondary:['联系平台客服','login']});}
function zsRenderReturnSuccess(){let data={};try{data=JSON.parse(sessionStorage.getItem('zs:return-success')||'{}')}catch{}zsRenderState({kind:'success',icon:'✓',title:'退回申请已提交',message:'管理员将核验聊天截图和电话录音。审核通过后，领取时实际扣除的积分将返还。',detail:[['申请编号',data.id||'已生成'],['客资',data.lead||'当前客资'],['申请返还',data.points?`${data.points} 积分`:'以审核结果为准'],['当前状态','待审核']],primary:['查看退回进度','leads?status=RETURN_PENDING'],secondary:['返回我的客资','leads']});}
function zsRenderState({kind='warn',icon='!',title,message,detail=[],primary,secondary}){const app=document.querySelector('#app');if(!app)return;document.body.classList.remove('zs-v13-auth-route');zsSetSafeHtml(app, `<main class="zs-v13-state-page"><div class="zs-v13-state-brand"><img src="./logo.png" alt="合家美宅"><span>合家美宅</span></div><section class="zs-v13-state-card"><div class="zs-v13-state-icon ${kind}">${zsStatusEsc(icon)}</div><h1>${zsStatusEsc(title)}</h1><p>${zsStatusEsc(message)}</p>${detail.length?`<div class="zs-v13-state-detail">${detail.map(([a,b])=>`<div><span>${zsStatusEsc(a)}</span><b>${zsStatusEsc(b)}</b></div>`).join('')}</div>`:''}</section><div class="zs-v13-state-actions">${primary?`<button class="btn btn-primary" data-zs-status-route="${zsStatusEsc(primary[1])}">${zsStatusEsc(primary[0])}</button>`:''}${secondary?`<button class="btn btn-outline" data-zs-status-route="${zsStatusEsc(secondary[1])}">${zsStatusEsc(secondary[0])}</button>`:''}</div></main>`);}
function zsPatchLinkLanding(){const active=/^#\/link\//.test(location.hash||'');document.body.classList.toggle('zs-v13-link-loading',active);if(!active)return;const main=document.querySelector('main.content');if(!main||main.querySelector('.zs-v13-link-landing'))return;main.innerHTML='<section class="zs-v13-link-landing"><i>↗</i><h2>正在进入客资详情</h2><p>系统正在校验微信身份、加盟商公司、订单状态和深链签名。</p><div class="zs-v13-loading-dots"><b></b><b></b><b></b></div></section>';}
function zsPatchInvalidLink(){const empty=document.querySelector('main.content .empty');if(!empty||!/(链接已失效|已被回收|页面加载失败)/.test(empty.textContent||''))return false;if(empty.dataset.zsSecure==='1')return true;empty.dataset.zsSecure='1';empty.innerHTML='<div class="zs-v13-state-icon">⌁</div><h2>该链接已失效</h2><p>客资可能已被领取、回收、释放，或当前账号无权访问。为保护客户隐私，本页面不展示任何客资摘要。</p><button class="btn btn-primary" data-zs-status-route="leads">返回客资列表</button>';document.body.classList.remove('zs-v13-link-loading');return true;
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
