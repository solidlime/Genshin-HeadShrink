"""diag_mizuki_files.py — inspect mizuki/ file naming convention."""
import re
import struct
from pathlib import Path

MIZUKI = Path(r"G:\XXMI-Launcher-Portable\Mods\mizuki")

# 1. Sample file naming
print("[1] Sample file names in mizuki/:")
all_files = sorted(MIZUKI.iterdir(), key=lambda p: p.name)
sample_names = [p.name for p in all_files[:10]]
print(f"    First 10: {sample_names}")
# Frame numbers
frame_nums = set()
for p in all_files:
    m = re.match(r'^(\d{6})-', p.name)
    if m:
        frame_nums.add(int(m.group(1)))
if frame_nums:
    print(f"    Frame numbers seen: {sorted(frame_nums)[:10]} ... (total: {len(frame_nums)} frames)")

# 2. Files with vb0 prefix (any frame)
print("\n[2] Files containing 'vb0' across all frames:")
vb0_files = sorted([p for p in all_files if 'vb0' in p.name])
print(f"    Total: {len(vb0_files)}")
if vb0_files:
    sizes = [p.stat().st_size for p in vb0_files[:20]]
    print(f"    First 20 names: {[p.name for p in vb0_files[:5]]}")
    print(f"    First 20 sizes: {sizes}")

# 3. Find ib files
print("\n[3] Files containing 'ib' (index buffer):")
ib_files = sorted([p for p in all_files if re.search(r'(?<![a-z])ib(?![a-z])', p.name)])
print(f"    Total: {len(ib_files)}")
if ib_files:
    print(f"    First 5: {[p.name for p in ib_files[:5]]}")
    print(f"    First 5 sizes: {[p.stat().st_size for p in ib_files[:5]]}")

# 4. Look at the largest vb0 file
print("\n[4] Largest vb0 files:")
big = sorted(vb0_files, key=lambda p: -p.stat().st_size)[:5]
for p in big:
    print(f"    {p.name}: {p.stat().st_size}B  (={p.stat().st_size/40:.1f} verts at stride=40)")
