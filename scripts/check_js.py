#!/usr/bin/env python3
from __future__ import annotations
import pathlib, subprocess, sys
root = pathlib.Path(__file__).resolve().parents[1]
files = [p for p in root.glob('apps/**/*.js') if 'vendor' not in p.parts]
failed=[]
for p in files:
    r=subprocess.run(['node','--check',str(p)],capture_output=True,text=True)
    if r.returncode:
        failed.append((p,r.stderr))
if failed:
    for p,e in failed: print(p,e)
    raise SystemExit(1)
print(f'checked {len(files)} JavaScript files')
