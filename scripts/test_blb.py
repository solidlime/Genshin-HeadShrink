"""Test Blb parser on the Nilou .blk file."""
import sys, os, io
sys.path.insert(0, r"G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts")
from blb_parser import Blb3File

BLK = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
OUT_DIR = r"D:\Documents\Default Project\Nilou\extracted"
os.makedirs(OUT_DIR, exist_ok=True)

print(f"Loading {BLK}")
blb = Blb3File(BLK)
print(f"  blocks: {len(blb.blocks)}")
for i, b in enumerate(blb.blocks):
    print(f"    [{i}] comp={b.compressed_size:,}  uncomp={b.uncompressed_size:,}  flags=0x{b.flags:x}")
print(f"  nodes: {len(blb.nodes)}")
for n in blb.nodes[:10]:
    print(f"    {n}")
print(f"  total uncomp: {sum(b.uncompressed_size for b in blb.blocks):,}")

# Extract first block and check for UnityFS magic
print("\nDecompressing block 0...")
block0 = blb.decompress_block(0)
print(f"  block0 size: {len(block0):,}")
print(f"  first 32 bytes: {block0[:32].hex()}")

# Decompress all and look for UnityFS / asset names
print("\nDecompressing all blocks...")
try:
    full = blb.decompress_all()
    print(f"  total decompressed: {len(full):,}")
    print(f"  first 32 bytes: {full[:32].hex()}")
    # Look for 'UnityFS' magic anywhere
    idx = full.find(b"UnityFS")
    if idx >= 0:
        print(f"  Found UnityFS at offset {idx}")
    # Look for 'Nilou' string
    nidx = full.find(b"Nilou")
    print(f"  'Nilou' at: {nidx}")

    # Save full decompressed to disk
    with open(os.path.join(OUT_DIR, "nilou_bundle.bin"), "wb") as f:
        f.write(full)
    print(f"  saved to {OUT_DIR}\\nilou_bundle.bin")
except Exception as e:
    print(f"  ERROR: {e!r}")
    import traceback; traceback.print_exc()
