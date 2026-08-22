"""Full Mitya decompress + UnityPy scan for Mesh."""
import sys, ctypes
from pathlib import Path
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser
from oodle import oodle_decompress
import lz4.block

BLK = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks\00\00514567.blk'
OUT = Path(r'D:\Documents\Default Project\Nilou\mitya_full_decompressed.bin')

with open(BLK, 'rb') as f:
    data = f.read()

import re
positions = [m.start() for m in re.finditer(b'Blb\x03', data)]
print(f'Mitya total bundles: {len(positions)}')

all_dec = bytearray()
for pos in positions:
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
    except Exception as e:
        print(f'  pos={pos:#x}: {e}')

print(f'Mitya decompressed: {len(all_dec)} bytes')
OUT.write_bytes(bytes(all_dec))

import UnityPy
from collections import Counter
env = UnityPy.load(str(OUT))
type_counts = Counter()
mesh_list = []
for obj in env.objects:
    try:
        tname = obj.type.name
        type_counts[tname] += 1
        if tname == 'Mesh':
            mesh_list.append(obj)
    except:
        type_counts['?unknown'] += 1

print(f'\nMitya UnityPy objects: {len(env.objects)}')
print(f'Types: {dict(type_counts)}')
print(f'Mesh count: {len(mesh_list)}')
if mesh_list:
    for m in mesh_list[:10]:
        try:
            print(f'  {m.m_Name}')
        except:
            pass