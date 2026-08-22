from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "scripts/_agent_invite_orchestrator_v3_20260822.py"
text = path.read_text(encoding="utf-8")
anchor = '''    for pattern in patterns:
        for path in ROOT.glob(pattern):
            path.unlink(missing_ok=True)
'''
replacement = anchor + '''    (ROOT / "docs/reports/INVITE-AUTHORITATIVE-FAILURE.md").unlink(missing_ok=True)
'''
if replacement not in text:
    if anchor not in text:
        raise RuntimeError("temporary cleanup anchor not found")
    text = text.replace(anchor, replacement, 1)
path.write_text(text, encoding="utf-8")
print("stale failure evidence cleanup added")
