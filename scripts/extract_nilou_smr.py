"""Fixed: load_all_bundles returns (offset, Blb3File) tuples. Use decompress_all() for raw bytes."""
import os
import sys
import time

try:
    import UnityPy
except ImportError:
    print("UnityPy not installed")
    sys.exit(1)

sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
from blb_parser import load_all_bundles

BLK = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\08476697.blk'
OUT_DIR = r'D:\Documents\Default Project\Nilou\anime_nilou_08476697_unbundled'
os.makedirs(OUT_DIR, exist_ok=True)

print(f"Loading {BLK}")
all_bundles = load_all_bundles(BLK)
print(f"Loaded {len(all_bundles)} bundles (each is (offset, Blb3File) tuple)")

# Decompress all bundles, save as raw bytes
bundle_data_list = []
for i, (offset, blb3file) in enumerate(all_bundles):
    try:
        data = blb3file.decompress_all()
    except Exception as e:
        continue
    if not data:
        continue
    bundle_data_list.append((i, offset, data))
    out_path = os.path.join(OUT_DIR, f'bundle_{i:04d}.bin')
    with open(out_path, 'wb') as out:
        out.write(data)

print(f"Decompressed {len(bundle_data_list)} bundles to {OUT_DIR}")

# Scan each bundle for SkinnedMeshRenderer + Animator + Mesh + Transform
print("\n=== Scanning bundles ===")
type_counts = {}
smr_bundles = []
animator_bundles = []
mesh_bundles = []
transform_bundles = []
gameobject_bundles = []

start = time.time()
for bundle_idx, offset, bundle_data in bundle_data_list:
    try:
        env = UnityPy.load(bundle_data)
        for obj in env.objects:
            tname = obj.type.name
            type_counts[tname] = type_counts.get(tname, 0) + 1
            if tname == 'SkinnedMeshRenderer':
                smr_bundles.append((bundle_idx, obj.path_id))
            elif tname == 'Animator':
                animator_bundles.append((bundle_idx, obj.path_id))
            elif tname == 'Mesh':
                mesh_bundles.append((bundle_idx, obj.path_id))
            elif tname == 'Transform':
                transform_bundles.append((bundle_idx, obj.path_id))
            elif tname == 'GameObject':
                gameobject_bundles.append((bundle_idx, obj.path_id))
    except Exception:
        pass

    if (bundle_idx + 1) % 100 == 0:
        elapsed = time.time() - start
        rate = (bundle_idx + 1) / elapsed
        eta = (len(bundle_data_list) - bundle_idx - 1) / rate
        print(f"  [{bundle_idx+1}/{len(bundle_data_list)}] {elapsed:.0f}s, ~{eta:.0f}s remaining", flush=True)

print(f"\nTotal types found:")
for tname, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {tname:30s} {count:>6}")

print(f"\nSkinnedMeshRenderer: {len(smr_bundles)}")
for bidx, pid in smr_bundles[:10]:
    print(f"  bundle {bidx}  pathID={pid}")
print(f"\nAnimator: {len(animator_bundles)}")
for bidx, pid in animator_bundles[:10]:
    print(f"  bundle {bidx}  pathID={pid}")
print(f"\nMesh: {len(mesh_bundles)}")
for bidx, pid in mesh_bundles[:20]:
    print(f"  bundle {bidx}  pathID={pid}")
print(f"\nTransform: {len(transform_bundles)}")
print(f"GameObject: {len(gameobject_bundles)}")

# If SkinnedMeshRenderer found, dump bone list
if smr_bundles:
    print(f"\n=== SkinnedMeshRenderer bones ===")
    for bidx, pid in smr_bundles[:3]:
        for idx, off, data in bundle_data_list:
            if idx == bidx:
                env = UnityPy.load(data)
                for obj in env.objects:
                    if obj.type.name == 'SkinnedMeshRenderer' and obj.path_id == pid:
                        try:
                            smr = obj.read()
                            print(f"  Bundle {bidx} SmR pathID={pid}")
                            print(f"    bones count: {len(smr.m_Bones)}")
                            for i, bone in enumerate(smr.m_Bones[:30]):
                                try:
                                    bone_obj = bone.read()
                                    print(f"      bone[{i}]: {bone_obj.m_Name}")
                                except Exception as e:
                                    print(f"      bone[{i}]: <{e}>")
                        except Exception as e:
                            print(f"  Bundle {bidx} SmR read error: {e}")
                break
