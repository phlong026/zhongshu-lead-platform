from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "scripts/_agent_invite_orchestrator_v3_20260822.py"
text = path.read_text(encoding="utf-8")
old = '''    execute_script("scripts/_agent_invite_authoritative_hotfix_20260822.py")
    execute_script("scripts/_agent_invite_authoritative_20260822.py")
'''
new = '''    restore_from_history("scripts/_agent_invite_authoritative_20260822.py")
    execute_script("scripts/_agent_invite_authoritative_hotfix_20260822.py")
    execute_script("scripts/_agent_invite_authoritative_20260822.py")
'''
if old not in text and new not in text:
    raise RuntimeError("authoritative restore-order anchor not found")
if old in text:
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("authoritative restore order corrected")
