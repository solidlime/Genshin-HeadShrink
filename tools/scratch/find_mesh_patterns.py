"""Search Nilou data for mesh-related string patterns - wider net."""
from pathlib import Path

NILOU = Path(r'D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin')
ndata = NILOU.read_bytes()

# Patterns to search (using bytes)
patterns = [
    b'SkinnedMeshRenderer',
    b'MeshRenderer',
    b'MeshFilter',
    b'_Skl_',
    b'_Sk_',
    b'_Mesh_',
    b'_Tex_',
    b'_Mat_',
    b'_Body',
    b'_Face',
    b'_Bang',
    b'_Pupil',
    b'_Brow',
    b'_Eye',
    b'RootBone',
    b'Nilou_Model',
    b'Nilou_Mesh',
    b'Nilou_Body',
    b'Nilou_Face',
    b'Nilou_Bang',
    b'Nilou_Hair',
    b'Nilou_Dress',
    b'Nilou_Skl',
    b'Nilou_Skinned',
    b'_Skinned_',
]

print(f'Nilou data size: {len(ndata):,}')
for pat in patterns:
    offsets = []
    i = 0
    while True:
        j = ndata.find(pat, i)
        if j < 0: break
        offsets.append(j)
        i = j + 1
    if offsets:
        # Show first few with context
        samples = []
        for off in offsets[:3]:
            # Try to extract a printable name
            start = off
            while start > 0 and ndata[start-1] not in (0, 0x0a, 0x0d, 0x09) and 32 <= ndata[start-1] < 127:
                start -= 1
            end = ndata.find(b'\x00', off)
            if end < 0 or end > off + 100: end = off + 60
            samples.append(f'0x{off:08x}={ndata[start:end]!r}')
        print(f'  {pat.decode():30s} {len(offsets):4d} hits. First: {", ".join(samples)}')
    else:
        print(f'  {pat.decode():30s}    0 hits')

# Also dump 100 bytes around the first Nilou match for inspection
print('\n--- Context around first Avatar_Girl_Sword_Nilou (offset 0x0d116b20) ---')
off = 0x0d116b20
print(f'bytes [0x{off-32:x}:0x{off+64:x}]:')
print(ndata[off-32:off+64].hex(' '))
# Try to extract readable chars around it
ctx = ndata[off-200:off+200]
print('readable ASCII chunk:', ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx))

# Look for known body part names WITHOUT Avatar_ prefix
print('\n--- Direct part names (no prefix) ---')
for pat in [b'_Body\x00', b'_Face\x00', b'_Bang\x00', b'Body_Eye\x00', b'Face_Eye\x00']:
    cnt = ndata.count(pat)
    if cnt > 0:
        off = ndata.find(pat)
        end = ndata.find(b'\x00', off)
        if end < 0: end = off + 60
        print(f'  {pat[:20]:20s}: {cnt} hits. First at 0x{off:x} = {ndata[off:end]!r}')