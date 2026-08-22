# -*- coding: utf-8 -*-
"""Analyze team-screen dump log.txt: multi-dispatch / gate-race evidence."""
import re
import sys
from collections import Counter

p = r'G:\XXMI-Launcher-Portable\Tools\HeadShrink\assets\Dump\編成画面口メッシュ潰れ\log.txt'
lines = open(p, encoding='utf-8', errors='replace').read().splitlines()

frame = None
dispatches = []   # (frame, shadername, count)
gates = []        # (frame, section, var, val)
facechecks = []   # (frame, section, cond)
maps_face = []
for l in lines:
    fm = re.search(r'\b(\d{6}) 3DMigoto', l)
    if fm:
        frame = int(fm.group(1))
    mm = re.search(r'(\w+) 3DMigoto\s+\[customshader[^\]]*\\(\w+)\] Dispatch\((\d+)', l)
    if mm:
        dispatches.append((mm.group(1), mm.group(2), int(mm.group(3))))
    gm = re.search(r'\[(?:TextureOverride|CommandList)[^\]]*\\(\w+)\] \$(is|active) = (\d)', l)
    if gm:
        gates.append((frame, gm.group(1), gm.group(2), gm.group(3)))
    fc = re.search(r'\[TextureOverride[^\]]*\\(\w+)\] if \$is: (\w+)', l)
    if fc:
        facechecks.append((frame, fc.group(1), fc.group(2)))
    if 'Map(' in l and ('6192fe1c' in l or 'd265427c' in l):
        maps_face.append(frame)

print('=== Dispatch per shader ===')
c = Counter(d[1] for d in dispatches)
for k, v in c.most_common(40):
    print(f'{v:4d}  {k}')
print()
print('=== same-frame duplicate dispatches (multi-apply evidence) ===')
cf = Counter((d[0], d[1]) for d in dispatches)
multi = sorted((k, v) for k, v in cf.items() if v > 1)
print(len(multi), 'cases')
for k, v in multi[:30]:
    print(k, v)
print()
falses = [f for f in facechecks if f[2] == 'false']
print(f'=== face-part $is checks: {len(falses)} false / {len(facechecks)} total ===')
for f in falses[:25]:
    print(f)
print()
print('=== Map on mouth hashes: frames', sorted(set(maps_face)), 'count', len(maps_face))
print()
print('=== gate raises ($is=1 / $active=1) by frame ===')
g1 = [g for g in gates if g[3] == '1']
by_frame = {}
for f, sec, var, val in g1:
    by_frame.setdefault(f, []).append(sec)
for f in sorted(by_frame):
    print(f, by_frame[f])
