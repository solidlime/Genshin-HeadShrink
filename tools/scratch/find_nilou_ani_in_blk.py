"""Search all 1925 .blk files for Nilou-specific animation strings.

The MDB parser found 0 MdbComponent bundles for Nilou. The actual animation
data for Nilou must be in a separate .blk file. Look for:
- 'Nilou_Ani' (likely intro/outro)
- 'Nilou_Dance' (her signature dance animation)
- 'Nilou_Standby' (idle animation)
- 'Nilou_'
"""
import os
import sys
import time
import re

BLOCKS_DIR = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks'
PERSISTENT_DIR = r'G:\Epic Games\GenshinImpact\GenshinImpact_Data\Persistent\AssetBundles\blocks'

# Collect all .blk paths
all_blks = []
for d in [BLOCKS_DIR, PERSISTENT_DIR]:
    if os.path.exists(d):
        for sub in sorted(os.listdir(d)):
            sub_path = os.path.join(d, sub)
            if os.path.isdir(sub_path):
                for f in sorted(os.listdir(sub_path)):
                    if f.endswith('.blk'):
                        all_blks.append((os.path.join(sub_path, f), sub, f))

print(f"Total .blk files: {len(all_blks)}")

# Search patterns
patterns = [
    b'Avatar_Girl_Sword_Nilou_Ani',
    b'Avatar_Girl_Sword_Nilou_Dance',
    b'Avatar_Girl_Sword_Nilou_Standby',
    b'Avatar_Girl_Sword_Nilou_',
    b'Nilou_Ani',
    b'Nilou_Dance',
    b'Nilou_Standby',
    b'Nilou_',
]

results = {p: [] for p in patterns}
start = time.time()

for i, (path, sub, fname) in enumerate(all_blks):
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        continue

    for p in patterns:
        count = data.count(p)
        if count > 0:
            results[p].append((path, sub, fname, count))

    if (i + 1) % 200 == 0:
        elapsed = time.time() - start
        rate = (i + 1) / elapsed
        eta = (len(all_blks) - i - 1) / rate
        print(f"  [{i+1}/{len(all_blks)}] {elapsed:.0f}s, ~{eta:.0f}s remaining", flush=True)

elapsed = time.time() - start
print(f"\nScan complete in {elapsed:.0f}s")

# Report
print("\n=== NILOU-RELATED .BLK FILES ===")
for p in patterns:
    hits = results[p]
    if not hits:
        continue
    print(f"\nPattern: {p.decode()}")
    print(f"  Hits: {len(hits)} files")
    for path, sub, fname, count in sorted(hits[:30], key=lambda x: -x[3]):
        size = os.path.getsize(path)
        print(f"    {sub}/{fname}  ({size:,} bytes)  pattern_hits={count}")

# Save output
with open(r'D:\Documents\Default Project\Nilou\nilou_blk_candidates.txt', 'w') as f:
    f.write(f"# Nilou-related .blk files (searched {len(all_blks)} files)\n")
    for p in patterns:
        hits = results[p]
        if not hits:
            continue
        f.write(f"\n## Pattern: {p.decode()} ({len(hits)} files)\n")
        for path, sub, fname, count in sorted(hits, key=lambda x: -x[3]):
            size = os.path.getsize(path)
            f.write(f"  {sub}/{fname}  {size:,} bytes  hits={count}\n")

print(f"\nSaved to D:\\Documents\\Default Project\\Nilou\\nilou_blk_candidates.txt")
