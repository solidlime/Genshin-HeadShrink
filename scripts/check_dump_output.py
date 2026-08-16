"""Check dump output dir structure for SkinnedMeshRenderer/Material data."""
import os

OUTPUT = r'D:\Documents\Default Project\Nilou\anime_nilou_08476697_dump'
print(f"=== {OUTPUT} ===")
for root, dirs, files in os.walk(OUTPUT):
    rel = os.path.relpath(root, OUTPUT)
    print(f"  {rel}:")
    for f in sorted(files):
        size = os.path.getsize(os.path.join(root, f))
        print(f"    {f}  ({size:,} bytes)")

# Specifically look for SkinnedMeshRenderer or bone/weight data
print("\n=== Searching for SkinnedMeshRenderer/bone data ===")
import re
for root, dirs, files in os.walk(OUTPUT):
    for f in sorted(files):
        if f.endswith('.json') or f.endswith('.txt') or f.endswith('.obj'):
            path = os.path.join(root, f)
            with open(path, 'rb') as fh:
                chunk = fh.read(65536)
            for needle in [b'SkinnedMeshRenderer', b'Bip001', b'Bone', b'm_Bones', b'm_Weights']:
                if needle in chunk:
                    print(f"  {path} contains {needle.decode()}")
            # Check first OBJ for bones
            if f.endswith('.obj'):
                with open(path) as fh:
                    head = fh.read(2000)
                if 'g ' in head or 'usemtl' in head:
                    print(f"  {path} has groups/materials")
