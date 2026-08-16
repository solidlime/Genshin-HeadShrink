"""diag_mizuki_167.py — debug Mizuki_167.obj weird dots issue."""
import os
import re
import struct
from pathlib import Path

MIZUKI = Path(r"G:\XXMI-Launcher-Portable\Mods\mizuki")
OBJ = Path(r"D:\Documents\Default Project\Nilou\anime_nilou_08476697\Mesh\Mizuki_167.obj")

# 1. What 167-* files exist?
print("=" * 70)
print("[1] Files matching '167-*' in mizuki/:")
files_167 = sorted(MIZUKI.glob("167-*"))
for f in files_167[:30]:
    print(f"    {f.name:60s} {f.stat().st_size:>10d}B")
print(f"    Total: {len(files_167)} files")

# 2. frame 167 DrawIndexed entries from log.txt
print("\n" + "=" * 70)
print("[2] frame 167 DrawIndexed entries in log.txt:")
log_path = MIZUKI / "log.txt"
target_lines = []
with log_path.open('r', encoding='utf-8', errors='replace') as f:
    for i, line in enumerate(f, 1):
        if line.startswith('000167 '):
            target_lines.append((i, line.rstrip()))
print(f"    Total 167-* lines in log.txt: {len(target_lines)}")
for i, (ln, txt) in enumerate(target_lines):
    if 'DrawIndexed' in txt or 'IASetIndexBuffer' in txt or 'IASetVertexBuffers' in txt:
        print(f"    L{ln}: {txt[:160]}")

# 3. Mizuki_167.obj vertex / face stats
print("\n" + "=" * 70)
print(f"[3] Mizuki_167.obj stats: {OBJ.stat().st_size}B")
v_count = 0
f_count = 0
xs, ys, zs = [], [], []
with OBJ.open('r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('v '):
            parts = line.split()
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            xs.append(x); ys.append(y); zs.append(z)
            v_count += 1
        elif line.startswith('f '):
            f_count += 1
print(f"    verts: {v_count}, faces: {f_count}")
if xs:
    print(f"    X range: [{min(xs):.4f}, {max(xs):.4f}]")
    print(f"    Y range: [{min(ys):.4f}, {max(ys):.4f}]")
    print(f"    Z range: [{min(zs):.4f}, {max(zs):.4f}]")
    print(f"    X near-zero (|x|<0.001): {sum(1 for x in xs if abs(x)<0.001)}/{v_count}")
