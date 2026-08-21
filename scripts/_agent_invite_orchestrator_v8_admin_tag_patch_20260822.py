from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "scripts/_agent_invite_orchestrator_v6_admin_entry_patch_20260822.py"
text = path.read_text(encoding="utf-8")
if "import re" not in text.splitlines()[:5]:
    text = text.replace("from pathlib import Path\n", "from pathlib import Path\nimport re\n", 1)
old = '''if "vendor/qrcode.min.js" not in html:
    marker = '<script src="./app.js"></script>'
    if marker not in html:
        marker = '<script src="app.js"></script>'
    if marker not in html:
        raise RuntimeError("real admin app script tag not found")
    html = html.replace(marker, '<script src="./vendor/qrcode.min.js"></script>\\n  ' + marker, 1)
'''
new = '''if "vendor/qrcode.min.js" not in html:
    match = re.search(
        r'(<script[^>]+src=["\\'][^"\\']*app\\.js(?:\\?[^"\\']*)?["\\'][^>]*></script>)',
        html,
        flags=re.I,
    )
    if match is None:
        raise RuntimeError("real admin app script tag not found")
    marker = match.group(1)
    html = html[:match.start()] + '<script src="./vendor/qrcode.min.js"></script>\\n  ' + marker + html[match.end():]
'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise RuntimeError("admin script injection anchor not found")
path.write_text(text, encoding="utf-8")
print("versioned admin script tag supported")
