from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "scripts/_agent_invite_orchestrator_v3_20260822.py"
text = path.read_text(encoding="utf-8")
anchor = '''    try:
        execute_script("scripts/_agent_invite_retry_fixes_20260822.py")
    except RuntimeError as exc:
        if "cannot restore required asset" not in str(exc):
            raise
'''
addition = anchor + '''    execute_script("scripts/_agent_invite_orchestrator_v10_oauth_error_patch_20260822.py")
'''
if addition not in text:
    if anchor not in text:
        raise RuntimeError("post-generation patch anchor not found")
    text = text.replace(anchor, addition, 1)
path.write_text(text, encoding="utf-8")
print("OAuth error patch moved after all generators")
