const H5_API_PREFIX = '/api/v1';
const H5_RETURN_DRAFT_PREFIX = 'zhongshu:return:';
const H5_NATIVE_FETCH = window.fetch.bind(window);
let uploadSequence = 0;

function safeJson(value, fallback = {}) {
  try { return JSON.parse(value || 'null') || fallback; } catch { return fallback; }
}

function currentReturnUrl() {
  return `${location.pathname}${location.hash || '#/home'}`;
}

function ensureNetworkBanner() {
  let banner = document.querySelector('#h5-network-banner');
  if (navigator.onLine) {
    banner?.remove();
    return;
  }
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'h5-network-banner';
    banner.className = 'h5-network-banner';
    banner.setAttribute('role', 'status');
    banner.textContent = '当前网络不可用，恢复网络后可继续操作';
    document.body.prepend(banner);
  }
}

function setUploadStatus(text, visible = true) {
  let box = document.querySelector('#h5-upload-status');
  if (!box) {
    box = document.createElement('div');
    box.id = 'h5-upload-status';
    box.className = 'h5-upload-status';
    box.innerHTML = '<i></i><span></span>';
    document.body.appendChild(box);
  }
  box.querySelector('span').textContent = text;
  box.hidden = !visible;
}

window.fetch = async function enhancedFetch(input, init = {}) {
  const url = typeof input === 'string' ? input : input.url;
  const isApi = url.startsWith(H5_API_PREFIX) || url.includes('/api/v1/');
  const isEvidence = /\/returns\/[^/]+\/evidence/.test(url);
  const controller = isApi ? new AbortController() : null;
  const timeout = controller ? setTimeout(() => controller.abort(), 30000) : null;
  if (isEvidence) {
    uploadSequence += 1;
    setUploadStatus(`正在上传证据 ${uploadSequence}`);
  }
  try {
    return await H5_NATIVE_FETCH(input, controller ? { ...init, signal: controller.signal } : init);
  } catch (error) {
    if (!navigator.onLine) ensureNetworkBanner();
    throw error;
  } finally {
    if (timeout) clearTimeout(timeout);
    if (isEvidence) setTimeout(() => setUploadStatus('', false), 500);
  }
};

function patchWechatLogin() {
  const button = document.querySelector('#wechat-login');
  if (!button || button.dataset.returnPatched === '1') return;
  button.dataset.returnPatched = '1';
  button.onclick = () => {
    const params = new URLSearchParams(location.hash.split('?')[1] || '');
    const invite = params.get('invite') || '';
    const returnUrl = currentReturnUrl();
    const query = new URLSearchParams({ return_url: returnUrl });
    if (invite) query.set('invite', invite);
    location.href = `${H5_API_PREFIX}/auth/wechat/start?${query.toString()}`;
  };
}

function renderFileSummary(input, selector) {
  const target = document.querySelector(selector);
  if (!target) return;
  zsSetSafeHtml(target, [...input.files].map(file =>
    `<div class="h5-file-chip"><span>${file.name.replace(/[<>&"']/g, '')}</span><small>${(file.size / 1024 / 1024).toFixed(2)}MB</small></div>`
  ).join(''));
}

function validateEvidencePage(event) {
  const button = event.target.closest('#submit-return');
  if (!button) return;
  const description = document.querySelector('#return-description')?.value.trim() || '';
  const screenshots = [...(document.querySelector('#screenshot-files')?.files || [])];
  const audio = document.querySelector('#audio-file')?.files?.[0];
  let message = '';
  if (description.length < 3) message = '请填写至少3个字的补充说明';
  else if (!screenshots.length) message = '请至少上传1张聊天或沟通截图';
  else if (screenshots.length > 5) message = '聊天截图最多上传5张';
  else if (screenshots.some(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024)) message = '截图仅支持 JPG/PNG/WEBP，单张不超过5MB';
  else if (!audio) message = '请上传电话录音';
  else {
    const ext = (audio.name.split('.').pop() || '').toLowerCase();
    if (audio.size > 20 * 1024 * 1024 || (!audio.type.startsWith('audio/') && !['m4a', 'mp3', 'wav', 'aac'].includes(ext))) message = '录音仅支持 M4A/MP3/WAV/AAC，单个不超过20MB';
  }
  if (message) {
    event.preventDefault();
    event.stopImmediatePropagation();
    const toast = document.querySelector('#toast');
    if (toast) {
      toast.textContent = message;
      toast.className = 'toast show error';
      setTimeout(() => { toast.className = 'toast'; }, 2600);
    }
  }
}

function patchReturnForm() {
  const description = document.querySelector('#return-description');
  const reason = document.querySelector('#return-reason');
  if (!description || !reason || description.dataset.draftPatched === '1') return;
  description.dataset.draftPatched = '1';
  const assignmentId = location.hash.split('/').pop()?.split('?')[0] || 'unknown';
  const key = `${H5_RETURN_DRAFT_PREFIX}${assignmentId}`;
  const saved = safeJson(localStorage.getItem(key));
  if (!description.value && saved.description) description.value = saved.description;
  if (saved.reason) reason.value = saved.reason;
  const save = () => localStorage.setItem(key, JSON.stringify({ reason: reason.value, description: description.value }));
  description.addEventListener('input', save);
  reason.addEventListener('change', save);

  const screenshots = document.querySelector('#screenshot-files');
  const audio = document.querySelector('#audio-file');
  if (screenshots) {
    const summary = document.createElement('div');
    summary.id = 'h5-screenshot-summary';
    screenshots.closest('.form-group')?.appendChild(summary);
    screenshots.addEventListener('change', () => renderFileSummary(screenshots, '#h5-screenshot-summary'));
  }
  if (audio) {
    const summary = document.createElement('div');
    summary.id = 'h5-audio-summary';
    audio.closest('.form-group')?.appendChild(summary);
    audio.addEventListener('change', () => renderFileSummary(audio, '#h5-audio-summary'));
  }
}

function patchLowPointsNotice() {
  if (document.querySelector('.h5-points-notice')) return;
  const balanceElement = [...document.querySelectorAll('.hero .balance')].find(el => /[\d,]+/.test(el.textContent || ''));
  if (!balanceElement) return;
  const balance = Number((balanceElement.textContent || '').replace(/[^\d.-]/g, ''));
  if (!Number.isFinite(balance) || balance >= 1000) return;
  const notice = document.createElement('div');
  notice.className = `h5-points-notice ${balance <= 0 ? 'danger' : ''}`;
  notice.innerHTML = `<b>${balance <= 0 ? '积分不足' : '积分余额偏低'}</b><span>当前余额低于预警值，余额不足时将无法继续领取客资，请联系平台线下充值。</span>`;
  balanceElement.closest('.hero')?.before(notice);
}

function patchPage() {
  patchWechatLogin();
  patchReturnForm();
  patchLowPointsNotice();
}

const observer = new MutationObserver(patchPage);
observer.observe(document.documentElement, { childList: true, subtree: true });
document.addEventListener('click', validateEvidencePage, true);
window.addEventListener('online', ensureNetworkBanner);
window.addEventListener('offline', ensureNetworkBanner);
window.addEventListener('hashchange', () => { uploadSequence = 0; });
ensureNetworkBanner();
patchPage();
