"""Check Body.obj format and try UnityPy for SkinnedMeshRenderer."""
import os

OBJ_DIR = r'D:\Documents\Default Project\Nilou\anime_nilou_08476697\Mesh'
body = os.path.join(OBJ_DIR, 'Body.obj')
print(f"Body.obj exists: {os.path.exists(body)}")
print(f"Body.obj size: {os.path.getsize(body):,}")

with open(body, 'rb') as f:
    chunk = f.read(2000)

# Check first 100 bytes
print(f"\nFirst 200 bytes (hex):")
print(' '.join(f'{b:02x}' for b in chunk[:200]))
print(f"\nFirst 200 bytes (text attempt):")
try:
    text = chunk.decode('utf-8', errors='replace')
    print(text[:500])
except Exception as e:
    print(f"Error: {e}")

# Check if it's text OBJ or binary
ascii_count = sum(1 for b in chunk if 32 <= b < 127 or b in (10, 13, 9))
print(f"\nASCII printable: {ascii_count}/200 ({100*ascii_count/200:.1f}%)")

# Look for common OBJ/FBX/markers
for marker in [b'# ', b'v ', b'f ', b'g ', b'vn ', b'vt ', b'BINARY', b'FBX', b'skinned', b'bone']:
    if marker in chunk:
        idx = chunk.find(marker)
        print(f"  Found marker {marker!r} at offset {idx}")
