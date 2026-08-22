"""Scan all 904 bundles for MdbComponent classID (0xA1CBB044) occurrences.

Also scans for Mesh classID (0x2B000000) in proper object table context.

The MdbComponent classID is 1152437153 = 0x44B0CBA1 = LE bytes A1 CB B0 44.
"""
import os
import sys
import struct
import time

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144
TOTAL_SIZE = 237167471
NUM_BUNDLES = TOTAL_SIZE // BUNDLE_SIZE  # 904

# Load file once
print("Loading 237MB file...", flush=True)
with open(NILOU_BIN, 'rb') as f:
    data = f.read()
print(f"Loaded {len(data):,} bytes", flush=True)

MDBC_MAGIC = b'\xa1\xcb\xb0\x44'  # MdbComponent classID LE
MESH_MAGIC = b'\x2b\x00\x00\x00'  # Mesh classID LE
UNITY_VER = b'2017.4.30f1\n'

mdb_bundles = []
mesh_bundles = []
both_bundles = []
unity_ver_bundles = []
start = time.time()

for bundle_idx in range(NUM_BUNDLES):
    offset = bundle_idx * BUNDLE_SIZE
    chunk = data[offset:offset + BUNDLE_SIZE]
    if len(chunk) < BUNDLE_SIZE:
        break

    mdb_count = chunk.count(MDBC_MAGIC)
    mesh_count = chunk.count(MESH_MAGIC)
    has_unity = UNITY_VER in chunk

    if has_unity:
        unity_ver_bundles.append(bundle_idx)
    if mdb_count > 0:
        mdb_bundles.append((bundle_idx, mdb_count))
    if mesh_count > 0:
        mesh_bundles.append((bundle_idx, mesh_count))
    if mdb_count > 0 and mesh_count > 0:
        both_bundles.append((bundle_idx, mdb_count, mesh_count))

    if (bundle_idx + 1) % 100 == 0:
        elapsed = time.time() - start
        rate = (bundle_idx + 1) / elapsed
        eta = (NUM_BUNDLES - bundle_idx - 1) / rate
        print(f"  [{bundle_idx+1}/{NUM_BUNDLES}] {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining, "
              f"unity={len(unity_ver_bundles)}, mdb={len(mdb_bundles)}, mesh={len(mesh_bundles)}, "
              f"both={len(both_bundles)}", flush=True)

print(f"\n=== RESULTS ===", flush=True)
print(f"Total bundles scanned: {NUM_BUNDLES}", flush=True)
print(f"Bundles with Unity version string: {len(unity_ver_bundles)}", flush=True)
print(f"Bundles with MdbComponent magic: {len(mdb_bundles)}", flush=True)
print(f"Bundles with Mesh magic: {len(mesh_bundles)}", flush=True)
print(f"Bundles with both: {len(both_bundles)}", flush=True)

print(f"\nFirst 30 MdbComponent bundles:", flush=True)
for bundle_idx, count in mdb_bundles[:30]:
    print(f"  bundle {bundle_idx:4d}  count={count}", flush=True)

print(f"\nFirst 30 Mesh bundles:", flush=True)
for bundle_idx, count in mesh_bundles[:30]:
    print(f"  bundle {bundle_idx:4d}  count={count}", flush=True)

# Save full reports
with open(r'D:\Documents\Default Project\Nilou\mdb_mdbc_bundles.txt', 'w') as f:
    f.write(f"# Total MdbComponent bundles: {len(mdb_bundles)}\n")
    for bundle_idx, count in mdb_bundles:
        f.write(f"{bundle_idx}\t{count}\n")

with open(r'D:\Documents\Default Project\Nilou\mdb_mesh_magic_bundles.txt', 'w') as f:
    f.write(f"# Total Mesh magic bundles: {len(mesh_bundles)}\n")
    for bundle_idx, count in mesh_bundles:
        f.write(f"{bundle_idx}\t{count}\n")

print(f"\nSaved to mdb_mdbc_bundles.txt and mdb_mesh_magic_bundles.txt", flush=True)
