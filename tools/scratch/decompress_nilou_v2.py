"""Step 6b: Re-decompress 02050112.blk correctly using decompress_all()
- Original test_nilou_full.py had bug: block_data[:blk.compressed_size] always
- Correct: use Blb3File.decompress_all() which uses proper offset accumulation
- Output: 1441 bundles concatenated, each is a Unity serialized file
"""
import sys
from pathlib import Path
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser
import lz4.block

BLK = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk'
OUT = Path(r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin')

with open(BLK, 'rb') as f:
    data = f.read()

import re
positions = [m.start() for m in re.finditer(b'Blb\x03', data)]
print(f'Total bundles: {len(positions)}')

# Decompress all bundles using decompress_all() (correct version)
all_dec = bytearray()
ok = 0
fail = 0
for i, pos in enumerate(positions):
    try:
        f3 = blb_parser.Blb3File(data, pos)
        dec = f3.decompress_all()
        all_dec += dec
        ok += 1
    except Exception as e:
        if i < 5:
            print(f'  Bundle {i} at 0x{pos:x} failed: {e}')
        fail += 1

print(f'OK={ok} FAIL={fail}, decompressed total: {len(all_dec):,} bytes')
OUT.write_bytes(bytes(all_dec))
print(f'Saved to {OUT}')

# Check first 64 bytes — should be Unity CAB header now
print(f'\nFirst 64 bytes of correctly decompressed data:')
for i in range(0, 64, 16):
    chunk = bytes(all_dec[i:i+16])
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f'  0x{i:08x}: {hex_str:<48s} {ascii_str}')
