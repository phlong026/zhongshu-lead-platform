from pathlib import Path

root = Path(__file__).resolve().parents[1]

# Patch full H5 generator and current H5 source.
for relative in ("scripts/_agent_invite_completion_20260822.py", "apps/h5/app.js"):
    path = root / relative
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "  AUTH_OAUTH_STATE_INVALID: '微信授权状态已失效，请重新进入。',",
        "  AUTH_OAUTH_STATE_INVALID: '微信授权状态已失效，请重新进入。',\n  AUTH_WECHAT_AUTH_FAILED: '微信授权失败，请重新打开专属邀请链接。',",
    )
    anchor = "  const invite = params.get('invite') || '';\n"
    addition = anchor + "  const callbackError = params.get('error') || '';\n  if (callbackError) { renderInviteFailure({code:callbackError}); return; }\n"
    if "const callbackError = params.get('error')" not in text and anchor in text:
        text = text.replace(anchor, addition, 1)
    path.write_text(text, encoding="utf-8")

# Patch the auth router itself. Invalid/tampered state remains a 400 AppError;
# only errors after a valid state has been established become H5 error pages.
router = root / "apps/api/src/routers/auth.py"
text = router.read_text(encoding="utf-8")
if "import logging" not in text.splitlines()[:8]:
    text = text.replace("from __future__ import annotations\n", "from __future__ import annotations\n\nimport logging\n", 1)
if "from urllib.parse import quote" not in text:
    text = text.replace("from typing import Annotated\n", "from typing import Annotated\nfrom urllib.parse import quote\n", 1)
if "logger = logging.getLogger" not in text:
    text = text.replace("router = APIRouter(prefix=\"/auth\", tags=[\"auth\"])\n", "router = APIRouter(prefix=\"/auth\", tags=[\"auth\"])\nlogger = logging.getLogger(\"zhongshu.auth.wechat\")\n", 1)
if "def _wechat_error_redirect(" not in text:
    marker = "def _safe_return_url(value: str | None) -> str:\n"
    helper = '''def _wechat_error_redirect(code: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/h5/#/login?error={quote(code, safe='')}",
        status_code=302,
    )


'''
    if marker not in text:
        raise RuntimeError("safe return URL anchor missing")
    text = text.replace(marker, helper + marker, 1)

old_exchange = '''    identity = client.exchange_code(code)
    if binding_flow:
        user, token, invite = bind_wechat_with_confirmation(
            db,
            state,
            openid=identity.openid,
            unionid=identity.unionid,
            nickname=identity.nickname or "微信加盟商",
            avatar_url=getattr(identity, "avatar_url", None),
        )
        target = confirmation_return_url(state)
        action = "WECHAT_BIND"
        metadata = {"invite_id": invite.id, "mode": "OAUTH"}
    else:
        user, token = login_bound_wechat(
            db,
            openid=identity.openid,
            unionid=identity.unionid,
            nickname=identity.nickname,
            avatar_url=getattr(identity, "avatar_url", None),
        )
        target = _safe_return_url(ordinary_state.get("return_url"))
        action = "WECHAT_OAUTH_LOGIN"
        metadata = {"mode": "OAUTH"}
'''
new_exchange = '''    try:
        identity = client.exchange_code(code)
    except Exception:
        logger.exception("WeChat OAuth code exchange failed")
        db.rollback()
        return _wechat_error_redirect("AUTH_WECHAT_AUTH_FAILED")

    try:
        if binding_flow:
            user, token, invite = bind_wechat_with_confirmation(
                db,
                state,
                openid=identity.openid,
                unionid=identity.unionid,
                nickname=identity.nickname or "微信加盟商",
                avatar_url=getattr(identity, "avatar_url", None),
            )
            target = confirmation_return_url(state)
            action = "WECHAT_BIND"
            metadata = {"invite_id": invite.id, "mode": "OAUTH"}
        else:
            user, token = login_bound_wechat(
                db,
                openid=identity.openid,
                unionid=identity.unionid,
                nickname=identity.nickname,
                avatar_url=getattr(identity, "avatar_url", None),
            )
            target = _safe_return_url(ordinary_state.get("return_url"))
            action = "WECHAT_OAUTH_LOGIN"
            metadata = {"mode": "OAUTH"}
    except AppError as exc:
        db.rollback()
        return _wechat_error_redirect(exc.code)
'''
if old_exchange in text:
    text = text.replace(old_exchange, new_exchange, 1)
elif "return _wechat_error_redirect(exc.code)" not in text:
    raise RuntimeError("OAuth exchange/binding anchor missing")
router.write_text(text, encoding="utf-8")

# Patch generated frontend contracts and browser smoke when already present.
front = root / "apps/api/tests/test_invite_frontend_contract.py"
if front.exists():
    text = front.read_text(encoding="utf-8")
    if "test_oauth_callback_errors_have_h5_status_contract" not in text:
        text += '''\n\ndef test_oauth_callback_errors_have_h5_status_contract() -> None:
    h5 = H5_APP.read_text(encoding="utf-8")
    auth = (ROOT / "apps/api/src/routers/auth.py").read_text(encoding="utf-8")
    assert "params.get('error')" in h5
    assert "AUTH_WECHAT_AUTH_FAILED" in h5
    assert "_wechat_error_redirect" in auth
    assert "return _wechat_error_redirect(exc.code)" in auth
'''
    front.write_text(text, encoding="utf-8")

browser = root / "apps/api/tests/test_invite_browser_smoke.py"
if browser.exists():
    text = browser.read_text(encoding="utf-8")
    if "test_h5_oauth_callback_error_renders_status_page" not in text:
        text += '''\n\ndef test_h5_oauth_callback_error_renders_status_page() -> None:
    with _static_server() as base, playwright.sync_playwright() as runner:
        browser = runner.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width":390,"height":844}, user_agent="Mozilla/5.0 MicroMessenger/8.0.50")
        page.goto(f"{base}/apps/h5/index.html#/login?error=AUTH_WECHAT_AUTH_FAILED")
        page.wait_for_selector("#invite-retry-button")
        assert "微信授权失败" in page.locator("body").inner_text()
        browser.close()
'''
    browser.write_text(text, encoding="utf-8")

print("OAuth callback H5 error routing completed")
