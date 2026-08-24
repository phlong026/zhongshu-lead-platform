const zsReturnIcon = (name, className='zs-svg-icon') => window.ZSIconSystem?.svg(name, className) || '';

function zsReturnRouteActive(){return /^#\/return\/[^/?]+/.test(location.hash||'');}
function zsSyncReturnRouteClass(){document.body.classList.toggle('zs-v13-return-route',zsReturnRouteActive());}
function zsRenderScreenshotPreviews(input,container){
  container.innerHTML='';[...input.files].slice(0,5).forEach(file=>{const img=document.createElement('img');img.alt='待上传截图预览';const url=URL.createObjectURL(file);img.src=url;img.onload=()=>URL.revokeObjectURL(url);container.appendChild(img);});
}
function zsPatchReturn(){
  zsSyncReturnRouteClass();if(!zsReturnRouteActive())return;
  const main=document.querySelector('main.content');if(!main)return;
  let wrapper=main.querySelector(':scope > .zs-v13-return-page');if(wrapper)return;
  const back=main.querySelector(':scope > .icon-btn');const title=main.querySelector(':scope > .page-title');const subtitle=main.querySelector(':scope > .subtitle');const stepper=main.querySelector(':scope > .stepper');const card=main.querySelector(':scope > .card');
  if(!back||!title||!subtitle||!stepper||!card)return;
  const heading=document.createElement('div');heading.className='zs-v13-return-heading';back.classList.add('zs-icon-label');zsSetSafeHtml(back, `${zsReturnIcon('chevron-left')}<span>返回</span>`);const h=document.createElement('h1');h.textContent='申请退回';const rules=document.createElement('button');rules.type='button';rules.textContent='审核规则';rules.onclick=()=>{const toast=document.querySelector('#toast');if(toast){toast.textContent='截图或电话录音任一类型满足即可，审核通过后返还积分';toast.className='toast show';setTimeout(()=>toast.className='toast',2600);}};heading.append(back,h,rules);
  const intro=document.createElement('div');intro.className='zs-v13-return-intro';zsSetSafeHtml(intro, `<b>${zsReturnIcon('alert-triangle')}</b><span></span>`);intro.querySelector('span').textContent=subtitle.textContent;
  const description=card.querySelector('#return-description');if(description){description.maxLength=200;const count=document.createElement('div');count.className='zs-v13-return-count';const sync=()=>count.textContent=`${description.value.length} / 200`;description.after(count);description.addEventListener('input',sync);sync();}
  const screenshot=card.querySelector('#screenshot-files');if(screenshot){const previews=document.createElement('div');previews.className='zs-v13-preview-grid';screenshot.closest('.upload')?.appendChild(previews);screenshot.addEventListener('change',()=>zsRenderScreenshotPreviews(screenshot,previews));}
  const audio=card.querySelector('#audio-file');if(audio){const preview=document.createElement('div');preview.className='zs-v13-audio-preview';preview.hidden=true;audio.closest('.upload')?.appendChild(preview);audio.addEventListener('change',()=>{const f=audio.files?.[0];preview.hidden=!f;if(f)zsSetSafeHtml(preview, `<span>${f.name.replace(/[<>&"']/g,'')}</span><b>${(f.size/1024/1024).toFixed(2)}MB</b>`);});}
  const confirm=document.createElement('div');confirm.className='zs-v13-return-confirm';zsSetSafeHtml(confirm, `<b>${zsReturnIcon('circle-check')}</b><span>我确认材料真实有效，并同意平台按规则审核。</span>`);const submit=card.querySelector('#submit-return');submit?.before(confirm);
  wrapper=document.createElement('div');wrapper.className='zs-v13-return-page';wrapper.append(heading,title,subtitle,intro,stepper,card);main.appendChild(wrapper);main.dataset.zsV13Return='1';
}
const zsReturnObserver=new MutationObserver(()=>queueMicrotask(zsPatchReturn));zsReturnObserver.observe(document.documentElement,{childList:true,subtree:true});window.addEventListener('hashchange',()=>queueMicrotask(zsPatchReturn));zsPatchReturn();
