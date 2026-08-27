const ERROR_META={
  AUTH_BINDING_REQUIRES_CLEAN_SESSION:['当前浏览器已登录平台账号。','请先退出该账号，再用加盟商负责人本人微信重新打开原邀请链接。'],
  AUTH_WECHAT_IDENTITY_CONFLICT:['当前微信身份与负责人记录不一致。','请联系平台管理员核对负责人微信绑定。'],
  AUTH_COMPANY_DISABLED:['该加盟商当前已停用。','请联系平台管理员确认主体状态。'],
  AUTH_COMPANY_ALREADY_BOUND:['该加盟商已完成负责人微信绑定。','如需更换负责人，请由平台先停用主体并解绑原负责人微信。'],
  AUTH_INVITE_INVALID:['邀请链接已失效。','请联系平台管理员重新生成邀请链接。'],
  AUTH_OAUTH_STATE_INVALID:['微信授权状态已失效。','请关闭当前页面，从原邀请链接重新进入。'],
  AUTH_BINDING_CONFIRM_REQUIRED:['本次绑定尚未完成身份确认。','请从原邀请链接进入并确认加盟商信息。'],
  AUTH_WECHAT_NOT_BOUND:['当前微信尚未绑定加盟商。','请使用平台发送的负责人邀请链接。'],
  AUTH_ACCOUNT_DISABLED:['当前账号已停用。','请联系平台管理员核对账号状态。'],
  WECHAT_NOT_CONFIGURED:['微信授权暂时不可用。','请稍后重试或联系平台管理员。'],
  WECHAT_OAUTH_UNAVAILABLE:['微信授权暂时不可用。','请稍后重试或联系平台管理员。'],
  WECHAT_OAUTH_FAILED:['微信授权未完成。','请稍后从原邀请链接重新进入。'],
  WECHAT_SCOPE_INVALID:['微信授权配置异常。','请联系平台管理员处理。'],
};

const params=new URLSearchParams(location.search);
const [message,action]=ERROR_META[params.get('code')]||['本次微信绑定未完成。','请联系平台管理员核对后重试。'];
document.querySelector('#auth-error-message').textContent=message;
document.querySelector('#auth-error-action').textContent=action;
history.replaceState(null,'',location.pathname);
