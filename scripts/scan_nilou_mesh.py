"""Scan all 1925 .blk files for Nilou mesh patterns."""
import os
import re
from pathlib import Path

BLOCKS_ROOT = Path(r"G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks")
PATTERNS = [
    b"Avatar_Girl_Sword_Nilou_Model_Body",
    b"Avatar_Girl_Sword_Nilou_Model_Face",
    b"Avatar_Girl_Sword_Nilou_Model_Bang",
    b"Avatar_Girl_Sword_Nilou_Model_Brow",
    b"Avatar_Girl_Sword_Nilou_Model_Pupil",
    b"Avatar_Girl_Sword_Nilou_Model_Face_Eye",
    b"Avatar_Girl_Sword_Nilou_Model_EyeStar",
    b"Avatar_Girl_Sword_Nilou_Model_EffectMesh",
    b"Avatar_Girl_Sword_Nilou_Model_EffectHair",
    b"Avatar_Girl_Sword_Nilou_Model_Hair",
    b"Avatar_Girl_Sword_Nilou_Model_Dress",
    b"Avatar_Girl_Sword_Nilou_Model_Body_LOD",
]

# Confirm-only patterns (reference, not mesh)
REF_PATTERNS = [
    b"Avatar_Girl_Sword_Nilou_Mat_",
    b"Avatar_Girl_Sword_Nilou_Tex_",
    b"Avatar_Girl_Sword_Nilou_",
]

results = {}
ref_only = {}

blk_files = []
for shard in sorted(BLOCKS_ROOT.iterdir()):
    if shard.is_dir() and shard.name.isdigit():
        for f in shard.glob("*.blk"):
            blk_files.append(f)
print(f"Total .blk files: {len(blk_files)}", flush=True)

for i, p in enumerate(blk_files):
    try:
        data = p.read_bytes()
    except (PermissionError, OSError) as e:
        print(f"  [{i+1}/{len(blk_files)}] SKIP {p.name}: {e}", flush=True)
        continue

    mesh_hits = {}
    for pat in PATTERNS:
        c = data.count(pat)
        if c > 0:
            mesh_hits[pat.decode()] = c
    if mesh_hits:
        results[p.name] = (p.stat().st_size, mesh_hits)
        print(f"  [{i+1}/{len(blk_files)}] {p.name} ({p.stat().st_size:,}B): MESH {mesh_hits}", flush=True)
        continue

    ref_hits = {}
    for pat in REF_PATTERNS:
        c = data.count(pat)
        if c > 0:
            ref_hits[pat.decode()[:40]] = c
    if ref_hits:
        ref_only[p.name] = (p.stat().st_size, ref_hits)

    if (i + 1) % 100 == 0:
        print(f"  [{i+1}/{len(blk_files)}] scanned", flush=True)

print(f"\n=== MESH-PATTERN HITS ({len(results)}) ===")
for name, (size, hits) in sorted(results.items(), key=lambda x: -sum(x[1][1].values())):
    total = sum(hits.values())
    print(f"  {name}  ({size:,}B)  total={total}  {hits}")

print(f"\n=== REF-ONLY (avatar prefix but no Mesh_*) ({len(ref_only)}) ===")
for name, (size, hits) in sorted(ref_only.items(), key=lambda x: -sum(x[1][1].values()))[:50]:
    total = sum(hits.values())
    print(f"  {name}  ({size:,}B)  total={total}  {list(hits.items())[:3]}")
print(f"  ... and {max(0, len(ref_only) - 50)} more")
