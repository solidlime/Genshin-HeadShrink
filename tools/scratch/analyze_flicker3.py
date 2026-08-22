# -*- coding: utf-8 -*-
"""Census all vb hashes per frame; find face-part candidates in gap frames."""
import re
from collections import defaultdict, Counter

p = r'G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-22-230007\log.txt'
lines = open(p, encoding='utf-8', errors='replace').read().splitlines()

frame = 0
vb_frames = defaultdict(set)     # hash -> frames where dumped
vb_sizes = {}                    # hash -> set of sizes
frame_vbs = defaultdict(list)    # frame -> [(hash, size)]

for l in lines:
    fm = re.match(r'\s*(\d{6}) 3DMigoto', l)
    if fm:
        frame = int(fm.group(1))
    dm = re.search(r'Dumping Buffer \S+\\(\d{6})-(vb\d+)=([0-9a-f]{8})\.bin', l)
    if dm:
        pass
    # actual format: NNNNNN 3DMigoto Dumping Buffer <path>\NNNNNN-vb0=HASH.bin
    dm = re.search(r'-(vb\d+)=([0-9a-f]{8})\.bin', l)
    if dm:
        vb, h = dm.group(1), dm.group(2)
        vb_frames[h].add(frame)

print('=== distinct dumped vb hashes:', len(vb_frames), '===')
# known face sizes: mouth 35080(877v), eyes 43320(1083v), brow 2240(56v); body vb0 638600
import os
d = p.rsplit('\\', 1)[0]
sizes = {}
for fn in os.listdir(d):
    m = re.match(r'\d{6}-(vb\d+)=([0-9a-f]{8})\.bin', fn)
    if m:
        sizes.setdefault(m.group(2), set()).add(os.path.getsize(os.path.join(d, fn)))

FACE_SIZES = {35080: 'mouth877', 43320: 'eyes1083', 2240: 'brow56'}
cands = []
for h, fs in sorted(vb_frames.items(), key=lambda kv: -len(kv[1])):
    sz = sizes.get(h, {'?'})
    tag = ''
    for s, name in FACE_SIZES.items():
        if s in sz:
            tag = f' <<< {name}'
            cands.append((h, len(fs)))
    print(f'{h} frames={len(fs):3d} sizes={sorted(sz)}{tag}')

print()
print('=== face-size candidate hashes ===')
for h, n in cands:
    print(h, sorted(vb_frames[h]))
