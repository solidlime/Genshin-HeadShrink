"""Step 3: Find which .blk files contain Nilou's referenced .asb hashes
- MDB extracted .asb paths: 66131/b62b4e6b80a7d847.asb, 66290/284f8f8a3a001b86.asb, etc.
- Search 1925 .blk files for these hashes
- The .asb might be embedded (sub-asset) inside a .blk
"""
import os, glob

# Nilou-referenced .asb hashes from MDB analysis
ASB_HASHES = [
    'b62b4e6b80a7d847',
    '284f8f8a3a001b86',
    '5e51e47d71876192',
    '62a845a4c0b5f03a',
    '21224b237a4d60cd',
    '866084b651f90a4f',
]

# Game data location
BLOCKS_DIR = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks'

# Find all .blk files
blk_files = []
for d in sorted(os.listdir(BLOCKS_DIR)):
    p = os.path.join(BLOCKS_DIR, d)
    if os.path.isdir(p):
        for f in os.listdir(p):
            if f.endswith('.blk'):
                blk_files.append(os.path.join(p, f))

print(f"Total .blk files: {len(blk_files)}")

# Search each hash in each .blk
for h in ASB_HASHES:
    print(f"\n=== Searching for .asb hash: {h} ===")
    matches = []
    for blk in blk_files:
        try:
            with open(blk, 'rb') as f:
                data = f.read()
            if h.encode() in data:
                matches.append(blk)
        except Exception as e:
            pass
    print(f"  Found in {len(matches)} .blk files:")
    for m in matches[:5]:
        print(f"    {m}")
    if len(matches) > 5:
        print(f"    ... and {len(matches) - 5} more")
