# -*- coding: utf-8 -*-
"""Flicker dump deep analysis: gate vs face-draw frame correlation."""
import re
from collections import defaultdict

p = r'G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-22-230007\log.txt'
lines = open(p, encoding='utf-8', errors='replace').read().splitlines()

HASHES = ['def7af36', 'd1384d15', '6192fe1c', 'd265427c', '63f702ce', 'ddf54429']
frame = 0
events = []            # (frame, lineno, kind, detail)
ischecks = []
dispatches = []

for i, l in enumerate(lines):
    fm = re.match(r'\s*(\d{6}) 3DMigoto', l)
    if fm:
        frame = int(fm.group(1))
    for h in HASHES:
        if h in l:
            kind = 'dump' if 'Dumping' in l else ('res' if 'resource=' in l else 'ref')
            events.append((frame, i + 1, h, kind, l.strip()[:110]))
    fc = re.search(r'\[TextureOverride[^\]]*\\(\w+)\] if \$is: (\w+)', l)
    if fc:
        ischecks.append((frame, fc.group(1), fc.group(2)))
    mm = re.search(r'\[customshader[^\]]*\\(\w+)\] Dispatch\((\d+)', l)
    if mm:
        dispatches.append((frame, mm.group(1)))

# per-frame view
by_frame = defaultdict(lambda: defaultdict(list))
for f, ln, h, kind, txt in events:
    by_frame[f][h].append((ln, kind))

all_frames = sorted(set(list(by_frame.keys()) + [f for f, _, _ in ischecks] + [f for f, _ in dispatches]))
print('=== frames containing any gate/face event ===')
print(' '.join(str(f) for f in all_frames))
print()
for f in all_frames:
    parts = []
    for h in HASHES:
        if h in by_frame[f]:
            kinds = [k for _, k in by_frame[f][h]]
            parts.append(f'{h}:{len(kinds)}({",".join(sorted(set(kinds)))})')
    chk = [f'{s.split("Noelle")[-1]}={r}' for ff, s, r in ischecks if ff == f]
    dsp = [f'{s}x{c}' for s, c in _count(dispatches, f)] if False else []
    from collections import Counter
    dsp = [f'{s}x{c}' for s, c in Counter(s for ff, s in dispatches if ff == f).items()]
    print(f'f{f:6d} | {" ".join(parts):55s} | chk: {" ".join(chk):40s} | disp: {" ".join(dsp)}')

def _count(d, f):
    return []
