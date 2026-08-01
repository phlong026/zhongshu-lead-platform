#!/usr/bin/env python3
from __future__ import annotations
import pathlib,re
root=pathlib.Path(__file__).resolve().parents[1]
patterns=[
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'(?i)(?:app_secret|jwt_secret|secret_access_key)\s*[=:]\s*["\'][^"\']{12,}["\']'),
]
ignore={'.git','docs/source'}
hits=[]
for p in root.rglob('*'):
    if not p.is_file() or any(part in ignore for part in p.parts): continue
    if p.suffix.lower() in {'.png','.jpg','.jpeg','.pdf','.xlsx','.docx','.zip','.db'}: continue
    try: text=p.read_text(encoding='utf-8')
    except Exception: continue
    for pat in patterns:
        if pat.search(text): hits.append((p,pat.pattern))
if hits:
    for h in hits: print(h)
    raise SystemExit(1)
print('no committed secrets detected')
