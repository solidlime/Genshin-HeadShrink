# -*- coding: utf-8 -*-
"""Analyze flicker dump: gate/hash alternation & skipped face sections per frame."""
import re
from collections import Counter, defaultdict

p = r'G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-22-230007\log.txt'
lines = open(p, encoding='utf-8', errors='replace').read().splitlines()

KNOWN_FACE = {'6192fe1c', 'd265427c', '63f702ce', 'ddf54429'}
frame = None
frames_seen = []
gate_frames = defaultdict(set)      # hash -> frames where bound
face_bind = defaultdict(list)       # hash -> [(frame, line_no)]
ischecks = []                       # (frame, section, result)
dispatches = []                     # (frame, shader)
pos_bind = []                       # d1384d15 binds

for i, l in enumerate(lines):
    fm = re.search(r'\b(\d{6}) 3DMigoto', l)
    if fm:
        f = int(fm.group(1))
        if not frames_seen or frames_seen[-1] != f:
            frames_seen.append(f)
        frame = f
    hm = re.search(r'\[TextureOverride[^\]]*\\(\w+)\] hash=([0-9a-f]{8})', l)
    if hm:
        h = hm.group(2)
        if h == 'def7af36':
            gate_frames['def7af36'].add(frame)
        elif h == 'd1384d15':
            pos_bind.append(frame)
        elif h in KNOWN_FACE:
            face_bind[h].append(frame)
    gm = re.search(r'\[(?:TextureOverride|CommandList)[^\]]*\\(\w+)\] \$(is) = (\d)', l)
    if gm:
        pass
    fc = re.search(r'\[TextureOverride[^\]]*\\(\w+)\] if \$is: (\w+)', l)
    if fc:
        ischecks.append((frame, fc.group(1), fc.group(2)))
    mm = re.search(r'\[customshader[^\]]*\\(\w+)\] Dispatch\((\d+)', l)
    if mm:
        dispatches.append((frame, mm.group(1)))

print('frames:', len(frames_seen), 'range', frames_seen[0], '-', frames_seen[-1])
print()
print('=== gate def7af36 bind frames ===')
gf = sorted(gate_frames.get('def7af36', []))
print('count:', len(gf), 'frames:', gf[:40])
print()
print('=== position d1384d15 bind frames ===')
pf = sorted(set(pos_bind))
print('count:', len(pf), 'frames:', pf[:40])
print()
print('=== face hash bind frames ===')
for h in sorted(face_bind):
    fs = sorted(set(x for x in face_bind[h]))
    print(h, 'count:', len(fs), 'frames:', fs[:40])
print()
print('=== $is checks by frame (section:result) ===')
byf = defaultdict(list)
for f, sec, r in ischecks:
    byf[f].append(f'{sec}:{r}')
for f in sorted(byf):
    print(f, byf[f])
print()
print('=== dispatches per frame ===')
df = Counter(dispatches)
per_frame = defaultdict(list)
for (f, s), c in df.items():
    per_frame[f].append((s, c))
for f in sorted(per_frame):
    print(f, per_frame[f])
