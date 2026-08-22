"""02050112.blk → Oodle full decompress → CAB ObjectInfo → classID distribution."""
import sys, struct, io
from pathlib import Path
from collections import Counter

sys.path.insert(0, r"G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts")
from blb_parser import Blb3File, scan_bundles

BLK = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk"

with open(BLK, "rb") as f:
    data = f.read()

bundles = scan_bundles(data)
print(f"[1] Bundles: {len(bundles)}")
if not bundles:
    sys.exit(1)

# Pick the first bundle, decompress all blocks
off, b = bundles[0]
print(f"[2] First bundle at offset {off:#x}, blocks={len(b.blocks)}, nodes={len(b.nodes)}")
flag_counts = Counter(blk.flags for blk in b.blocks)
print(f"[3] Block flags: {dict(flag_counts)}")

print("[4] Decompressing all blocks...")
try:
    raw = b.decompress_all()
    print(f"    decompressed size: {len(raw):,} bytes")
except Exception as e:
    print(f"    FAILED: {e}")
    sys.exit(1)

# Parse all nodes (CABs) and aggregate type/classID
print("[5] Parsing CAB ObjectInfo tables...")
cab_dist = Counter()
total_objs = 0
errors = 0
for i, node in enumerate(b.nodes):
    if node["is_dir"]:
        continue
    start = node["offset"]
    end = start + node["size"]
    if end > len(raw):
        errors += 1
        continue
    cab = raw[start:end]
    try:
        if cab[:4] not in (b"!!\x06\x06", b"\x00\x00\x00\x00", b"!!\x04\x04"):
            # Might be compressed/encrypted CAB; skip for now
            if len(cab) < 20:
                continue
        # Try as SerializedFile (Unity standard)
        # Header: m_MetadataSize(u32), m_FileSize(u32), m_Version(u32), m_DataOffset(u32)
        if len(cab) < 16:
            continue
        meta_size, file_size, version, data_offset = struct.unpack("<IIII", cab[:16])
        if meta_size > len(cab) or file_size > len(cab) + 1024 or version > 100:
            continue
        # Parse type list
        if meta_size < 16 + 4:
            continue
        cur = 16
        # type count (in CAB v17+)
        type_count = struct.unpack("<i", cab[cur:cur+4])[0]
        cur += 4
        type_ids = []
        for _ in range(type_count):
            if cur + 16 > len(cab):
                break
            # SerializedType: classID(i32), strip(u8), data (16 bytes hash)
            class_id = struct.unpack("<i", cab[cur:cur+4])[0]
            type_ids.append(class_id)
            cur += 20
        for cid in type_ids:
            cab_dist[cid] += 1
        total_objs += type_count
    except Exception:
        errors += 1

print(f"\n[6] Total types parsed: {total_objs}, errors: {errors}")
print(f"[7] Top classIDs across {len([n for n in b.nodes if not n['is_dir']])} CABs:")
for cid, cnt in cab_dist.most_common(30):
    name = {
        43: "Mesh",
        28: "Texture2D",
        21: "Material",
        95: "Animator",
        74: "AnimationClip",
        115: "MonoBehaviour",
        120: "MonoScript",
        1001: "AssetBundle",
        114: "MonoBehaviour (old)",
        28: "Texture2D",
        329: "Shader",
        1: "GameObject",
        4: "Transform",
        224: "RectTransform",
    }.get(cid, "?")
    print(f"    {cid:>10} (0x{cid & 0xFFFFFFFF:08X}) {name:>20} : {cnt}")