"""Try UnityPy on Nilou 02050112.blk full decompressed data."""
import sys, ctypes
from pathlib import Path
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser
from oodle import oodle_decompress
import lz4.block

BLK = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk'
OUT = Path(r'D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin')

with open(BLK, 'rb') as f:
    data = f.read()

import re
positions = [m.start() for m in re.finditer(b'Blb\x03', data)]
print(f'Total bundles: {len(positions)}')

# Decompress all bundles
all_dec = bytearray()
ok = 0
fail = 0
for i, pos in enumerate(positions):
    try:
        f3 = blb_parser.Blb3File(data, pos)
        for blk in f3.blocks:
            comp = bytearray(f3.block_data[:blk.compressed_size])
            if blk.compressed_size > 6:
                blb_parser.blb_decrypt(f3._hk, comp)
            comp_bytes = bytes(comp)
            if blk.flags == blb_parser.COMP_NONE:
                all_dec += comp_bytes[:blk.uncompressed_size]
            elif blk.flags in (blb_parser.COMP_LZ4, blb_parser.COMP_LZ4HC):
                all_dec += lz4.block.decompress(comp_bytes, uncompressed_size=blk.uncompressed_size)
            elif blk.flags == blb_parser.COMP_OODLE:
                all_dec += oodle_decompress(comp_bytes, blk.uncompressed_size)
        ok += 1
    except Exception as e:
        fail += 1

print(f'OK={ok} FAIL={fail}, decompressed total: {len(all_dec)} bytes')
OUT.write_bytes(bytes(all_dec))
print(f'Saved to {OUT}')

import UnityPy
env = UnityPy.load(str(OUT))
print(f'UnityPy: {len(env.objects)} objects')

# Count by type
from collections import Counter
type_counts = Counter()
mesh_objects = []
for obj in env.objects:
    try:
        tname = obj.type.name
        type_counts[tname] += 1
        if tname == 'Mesh':
            mesh_objects.append(obj)
    except:
        type_counts['?unknown'] += 1

print(f'\nType distribution:')
for t, c in sorted(type_counts.items(), key=lambda x: -x[1])[:30]:
    print(f'  {t}: {c}')

if mesh_objects:
    print(f'\nFOUND {len(mesh_objects)} Mesh objects!')
    for m in mesh_objects[:5]:
        try:
            print(f'  path_id={m.path_id} name={m.m_Name}')
        except:
            pass