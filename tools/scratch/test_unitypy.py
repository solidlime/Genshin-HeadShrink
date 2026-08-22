"""Try UnityPy on decompressed Mitya data."""
import sys, ctypes
from pathlib import Path
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser
from oodle import oodle_decompress
import lz4.block

BLK_MITYA = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks\00\00514567.blk'

with open(BLK_MITYA, 'rb') as f:
    data = f.read()

import re
positions = [m.start() for m in re.finditer(b'Blb\x03', data)]
print(f'Total bundles in Mitya: {len(positions)}')

# Decompress all bundles, concatenate
all_dec = bytearray()
for i, pos in enumerate(positions[:10]):
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

print(f'Decompressed {len(positions[:10])} bundles = {len(all_dec)} bytes')
print(f'First 32: {bytes(all_dec[:32]).hex(" ")}')

# Try UnityPy
try:
    import UnityPy
    env = UnityPy.load(bytes(all_dec))
    print(f'UnityPy loaded: {len(env.objects)} objects')
    for obj in env.objects:
        try:
            print(f'  {obj.type.name}: path_id={obj.path_id}')
        except Exception as e:
            print(f'  ERROR: {e}')
except Exception as e:
    print(f'UnityPy error: {type(e).__name__}: {str(e)[:200]}')

# Save to file and try UnityPy.file loading
out_path = Path(r'D:\Documents\Default Project\Nilou\test_mitya_decompressed.bin')
out_path.write_bytes(bytes(all_dec))
print(f'Saved to {out_path}')

try:
    env2 = UnityPy.load(str(out_path))
    print(f'UnityPy file load: {len(env2.objects)} objects')
except Exception as e:
    print(f'UnityPy file load error: {type(e).__name__}: {str(e)[:200]}')