"""Test multi-bundle scanning."""
import sys, os
sys.path.insert(0, r"G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts")
from blb_parser import load_all_bundles

BLK = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
OUT = r"D:\Documents\Default Project\Nilou\extracted"
os.makedirs(OUT, exist_ok=True)

bundles = load_all_bundles(BLK)
print(f"Found {len(bundles)} bundles")

# Print summary of each
for idx, (off, b) in enumerate(bundles[:30]):
    node_names = [n['name'] for n in b.nodes]
    print(f"  [{idx}] @{off:#x}  blocks={len(b.blocks)} nodes={len(b.nodes)}  names={node_names}")

# Try to decompress the FIRST bundle's blocks
print("\nAttempting block decompression on first 3 bundles...")
for idx, (off, b) in enumerate(bundles[:3]):
    print(f"\n[{idx}] @{off:#x}:")
    for bi, blk in enumerate(b.blocks):
        try:
            data = b.decompress_block(bi)
            print(f"  block {bi}: OK size={len(data):,}")
        except Exception as e:
            print(f"  block {bi}: ERROR {str(e)[:80]}")
