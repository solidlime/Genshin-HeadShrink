"""Pre-filter 904 bundles by Unity version string presence, then scan non-empty ones."""
import os
import struct
import sys
import time

try:
    import UnityPy
except ImportError:
    print("UnityPy not installed")
    sys.exit(1)

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144
TOTAL_SIZE = 237167471
NUM_BUNDLES = TOTAL_SIZE // BUNDLE_SIZE

print(f"File size: {TOTAL_SIZE:,}", flush=True)
print(f"Bundles: {NUM_BUNDLES} x {BUNDLE_SIZE:,} bytes", flush=True)

# Pattern: "2017.4.30f1\n" — 13 bytes — Unity version string
PATTERN = b"2017.4.30f1\n"

print("Loading file...", flush=True)
with open(NILOU_BIN, 'rb') as f:
    data = f.read()
print(f"Loaded {len(data):,} bytes", flush=True)

# Pre-filter: find all bundles with Unity version string
print("Pre-filtering by Unity version string...", flush=True)
valid_bundles = []
for bundle_idx in range(NUM_BUNDLES):
    offset = bundle_idx * BUNDLE_SIZE
    if PATTERN in data[offset:offset + BUNDLE_SIZE]:
        valid_bundles.append(bundle_idx)

print(f"Bundles with Unity version: {len(valid_bundles)}", flush=True)

# Now scan those valid bundles with UnityPy
print("Scanning valid bundles with UnityPy...", flush=True)
mesh_bundles = []
type_counts = {}
asb_paths = []
start = time.time()

for i, bundle_idx in enumerate(valid_bundles):
    offset = bundle_idx * BUNDLE_SIZE
    chunk = data[offset:offset + BUNDLE_SIZE]
    try:
        env = UnityPy.load(chunk)
        for obj in env.objects:
            tname = obj.type.name
            type_counts[tname] = type_counts.get(tname, 0) + 1
            if tname == 'Mesh':
                mesh_bundles.append((bundle_idx, offset, obj.path_id))
            if tname == 'AssetBundle':
                try:
                    tree = obj.read_typetree()
                    name = tree.get('m_Name', '')
                    asb_paths.append((bundle_idx, name))
                except Exception:
                    pass
    except Exception as e:
        print(f"  bundle {bundle_idx}: {type(e).__name__}: {e}", flush=True)

    if (i + 1) % 20 == 0:
        elapsed = time.time() - start
        rate = (i + 1) / elapsed
        eta = (len(valid_bundles) - i - 1) / rate
        print(f"  [{i+1}/{len(valid_bundles)}] {elapsed:.0f}s, ~{eta:.0f}s remaining, {len(mesh_bundles)} mesh so far", flush=True)

# Report
print(f"\n=== RESULTS ===", flush=True)
print(f"Total type counts (across valid bundles):", flush=True)
for tname, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {tname:30s} {count:>6}", flush=True)

print(f"\nMesh bundles: {len(mesh_bundles)}", flush=True)
for bundle_idx, offset, pid in mesh_bundles[:30]:
    print(f"  bundle {bundle_idx:4d}  offset=0x{offset:08x}  pathID={pid}", flush=True)

print(f"\nFirst 20 .asb paths:", flush=True)
for bundle_idx, name in asb_paths[:20]:
    print(f"  bundle {bundle_idx:4d}  {name}", flush=True)

print(f"\nTotal .asb paths: {len(asb_paths)}", flush=True)

# Save results
with open(r'D:\Documents\Default Project\Nilou\mdb_mesh_bundles.txt', 'w') as f:
    f.write(f"# MDB Mesh bundles from 02050112.blk\n")
    f.write(f"# Total: {len(mesh_bundles)} mesh bundles\n\n")
    for bundle_idx, offset, pid in mesh_bundles:
        f.write(f"{bundle_idx}\t0x{offset:08x}\t{pid}\n")
print(f"Saved: D:\\Documents\\Default Project\\Nilou\\mdb_mesh_bundles.txt", flush=True)

# Save asb -> bundle mapping
with open(r'D:\Documents\Default Project\Nilou\mdb_asb_paths.txt', 'w') as f:
    for bundle_idx, name in asb_paths:
        f.write(f"{bundle_idx}\t{name}\n")
print(f"Saved: D:\\Documents\\Default Project\\Nilou\\mdb_asb_paths.txt", flush=True)
