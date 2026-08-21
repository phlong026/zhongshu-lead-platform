from pathlib import Path

root = Path(__file__).resolve().parents[1]

# Patch the full generator so existing-login keeps the established enhancement hook.
full = root / "scripts/_agent_invite_completion_20260822.py"
if full.exists():
    text = full.read_text(encoding="utf-8")
    text = text.replace('id=\"wechat-existing-login\"', 'id=\"wechat-login\"')
    text = text.replace("'#wechat-existing-login'", "'#wechat-login'")
    full.write_text(text, encoding="utf-8")

h5 = root / "apps/h5/app.js"
if h5.exists():
    text = h5.read_text(encoding="utf-8")
    text = text.replace('id="wechat-existing-login"', 'id="wechat-login"')
    text = text.replace("'#wechat-existing-login'", "'#wechat-login'")
    h5.write_text(text, encoding="utf-8")

print("existing WeChat login compatibility hook preserved")
