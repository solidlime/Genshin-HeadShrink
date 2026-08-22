"""Try UnityPy on each bundle to find Mesh objects.

AssetStudio/UnityPy can parse Unity serialized files. If the bundle is a valid
serialized file, UnityPy will load it.
"""
import os
import sys
import struct

try:
    import UnityPy
except ImportError:
    print("UnityPy not installed")
    sys.exit(1)

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144
NUM_BUNDLES = 904  # 237167471 / 262144 ≈ 904

print(f"UnityPy version: {UnityPy.__version__ if hasattr(UnityPy, '__version__') else 'unknown'}")

# Try to load first 5 bundles
for bundle_idx in range(5):
    offset = bundle_idx * BUNDLE_SIZE
    with open(NILOU_BIN, 'rb') as f:
        f.seek(offset)
        data = f.read(BUNDLE_SIZE)
    print(f"\n=== Bundle {bundle_idx} (offset {offset}) ===")
    try:
        env = UnityPy.load(data)
        print(f"  Loaded! Type: {env.__class__.__name__}")
        objects = list(env.objects)
        print(f"  Total objects: {len(objects)}")
        type_counts = {}
        for obj in objects:
            tid = obj.type.name
            type_counts[tid] = type_counts.get(tid, 0) + 1
        print(f"  Type counts: {type_counts}")
        # Show details of first 5 objects
        for obj in objects[:5]:
            try:
                tree = obj.read_typetree()
                obj_name = tree.get('m_Name', '?')
                print(f"    {obj.type.name:30s} pathID={obj.path_id} name={obj_name!r}")
            except Exception as e:
                print(f"    {obj.type.name:30s} pathID={obj.path_id} (read_typetree: {e})")
    except Exception as e:
        print(f"  FAIL: {e}")
        # Show first 16 bytes for debugging
        print(f"  first 16 bytes: {data[:16].hex()}")
