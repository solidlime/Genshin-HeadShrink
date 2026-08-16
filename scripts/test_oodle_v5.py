"""Test Oodle with RAW data (no decrypt) and various skip patterns."""
import sys, ctypes
from pathlib import Path

sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser

BLK = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk'
OOZ = Path(r'D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\bin\AnimeStudio.Ooz.dll')
OO2 = Path(r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts\oo2core_9_win64.dll')

with open(BLK, 'rb') as f:
    data = f.read()
f3 = blb_parser.Blb3File(data, 0)
blk0 = f3.blocks[0]

# Three versions of compressed data
raw = bytes(f3.block_data[:blk0.compressed_size])  # NO decrypt
dec_full = bytearray(raw)
blb_parser.blb_decrypt(f3._hk, dec_full)  # Full decrypt (only first 128B changed)
dec_full = bytes(dec_full)

print(f'comp_size={blk0.compressed_size} uncomp={blk0.uncompressed_size}')
print(f'raw[0:16]    = {raw[:16].hex(" ")}')
print(f'dec_full[0:16] = {dec_full[:16].hex(" ")}')
print()

# Try various combos: oo2core_CDLL only (smaller test surface)
dll = ctypes.CDLL(str(OO2))
func = dll.OodleLZ_Decompress
func.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                 ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                 ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
func.restype = ctypes.c_int

for label, src_bytes, skip in [
    ('raw,skip=0', raw, 0),
    ('raw,skip=6', raw, 6),
    ('raw,skip=128', raw, 128),
    ('dec,skip=0', dec_full, 0),
    ('dec,skip=6', dec_full, 6),
    ('dec,skip=128', dec_full, 128),
]:
    src = src_bytes[skip:]
    src_view = (ctypes.c_uint8 * len(src)).from_buffer_copy(src)
    out = (ctypes.c_uint8 * blk0.uncompressed_size)()
    rc = func(ctypes.cast(src_view, ctypes.c_void_p), len(src),
              ctypes.cast(out, ctypes.c_void_p), blk0.uncompressed_size,
              1, 0, 0, 0, 0, 0, 0, 0, 0, 3)
    out_first = bytes(out[:16]).hex(' ') if rc > 0 else 'n/a'
    print(f'  {label}: src_len={len(src)} rc={rc} out_first={out_first}')