"""Scan all 904 bundles in nilou_full_v2.bin, find Mesh-bearing ones. With explicit flush."""
import os
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
NUM_BUNDLES = TOTAL_SIZE // BUNDLE_SIZE  # 904

print(f"Scanning {NUM_BUNDLES} bundles of {BUNDLE_SIZE} bytes", flush=True)

mesh_bundles = []
type_counts_global = {}
asb_paths = []
nonempty_bundles = 0
asb_to_bundle = {}
start = time.time()

# Load file once into memory? 237MB is OK
print("Loading 237MB file into memory...", flush=True)
with open(NILOU_BIN, 'rb') as f:
    data = f.read()
print(f"Loaded {len(data):,} bytes", flush=True)

for bundle_idx in range(NUM_BUNDLES):
    offset = bundle_idx * BUNDLE_SIZE
    chunk = data[offset:offset + BUNDLE_SIZE]
    if len(chunk) < BUNDLE_SIZE:
        break
    try:
        env = UnityPy.load(chunk)
        objects = list(env.objects)
        if not objects:
            continue
        nonempty_bundles += 1
        for obj in objects:
            tname = obj.type.name
            type_counts_global[tname] = type_counts_global.get(tname, 0) + 1
            if tname == 'Mesh':
                mesh_bundles.append((bundle_idx, offset, obj.path_id))
            if tname == 'AssetBundle':
                try:
                    tree = obj.read_typetree()
                    name = tree.get('m_Name', '')
                    asb_paths.append((bundle_idx, name))
                    asb_to_bundle[name] = bundle_idx
                except Exception:
                    pass
    except Exception as e:
        pass

    if (bundle_idx + 1) % 50 == 0:
        elapsed = time.time() - start
        rate = (bundle_idx + 1) / elapsed
        eta = (NUM_BUNDLES - bundle_idx - 1) / rate
        print(f"  [{bundle_idx+1}/{NUM_BUNDLES}] {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining, {nonempty_bundles} non-empty, {len(mesh_bundles)} mesh", flush=True)

# Report
print(f"\n=== RESULTS ===", flush=True)
print(f"Non-empty bundles: {nonempty_bundles}/{NUM_BUNDLES}", flush=True)
print(f"\nGlobal type counts:", flush=True)
for tname, count in sorted(type_counts_global.items(), key=lambda x: -x[1]):
    print(f"  {tname:30s} {count:>6}", flush=True)

print(f"\nMesh bundles: {len(mesh_bundles)}", flush=True)
for bundle_idx, offset, pid in mesh_bundles[:30]:
    print(f"  bundle {bundle_idx:4d}  offset=0x{offset:08x}  pathID={pid}", flush=True)

print(f"\nFirst 20 .asb paths:", flush=True)
for bundle_idx, name in asb_paths[:20]:
    print(f"  bundle {bundle_idx:4d}  {name}", flush=True)
print(f"... total {len(asb_paths)} AssetBundle entries", flush=True)

# Save mesh bundle info
with open(r'D:\Documents\Default Project\Nilou\mdb_mesh_bundles.txt', 'w') as f:
    f.write(f"# Total mesh bundles: {len(mesh_bundles)}\n")
    for bundle_idx, offset, pid in mesh_bundles:
        f.write(f"{bundle_idx}\t0x{offset:08x}\t{pid}\n")
print(f"\nSaved mesh bundle list to D:\\Documents\\Default Project\\Nilou\\mdb_mesh_bundles.txt", flush=True)

# Save asb name -> bundle mapping
with open(r'D:\Documents\Default Project\Nilou\mdb_asb_to_bundle.txt', 'w') as f:
    for name, bidx in sorted(asb_to_bundle.items()):
        f.write(f"{bidx}\t{name}\n")
print(f"Saved asb -> bundle map to D:\\Documents\\Default Project\\Nilou\\mdb_asb_to_bundle.txt", flush=True)
