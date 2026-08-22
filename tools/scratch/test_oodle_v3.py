"""Oodle decompression focused test - AnimeStudio.Ooz.dll with correct DLL path."""
import sys, ctypes
from pathlib import Path

sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser

BLK = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk'
OOZ = Path(r'D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\bin\AnimeStudio.Ooz.dll')
OO2 = Path(r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts\oo2core_9_win64.dll')

# Parse
with open(BLK, 'rb') as f:
    data = f.read()
f3 = blb_parser.Blb3File(data, 0)
print(f'uncompressed_size (1<<shift)={f3.uncompressed_size}, blocks={len(f3.blocks)}')
blk0 = f3.blocks[0]
print(f'block0: comp_size={blk0.compressed_size} uncomp_size={blk0.uncompressed_size} flags={blk0.flags:#x}')

# Read raw compressed block + decrypt manually (avoid recursion)
start = 0
compressed = bytearray(f3.block_data[start:start + blk0.compressed_size])
if blk0.compressed_size > 6:
    blb_parser.blb_decrypt(f3._hk, compressed)
print(f'decrypted block0: {len(compressed)} bytes, first 16B = {bytes(compressed[:16]).hex(" ")}')

# === Test 1: AnimeStudio.Ooz.dll via existing oodle.py ===
print('\n=== TEST 1: AnimeStudio.Ooz.dll via oodle.py ===')
try:
    from oodle import oodle_decompress
    out = oodle_decompress(bytes(compressed), blk0.uncompressed_size)
    print(f'  SUCCESS: {len(out)} bytes, first 16 = {out[:16].hex(" ")}')
except Exception as e:
    print(f'  FAIL: {type(e).__name__}: {e}')

# === Test 2: oo2core_9_win64.dll CDLL + skip variants ===
print('\n=== TEST 2: oo2core_9_win64.dll CDLL ===')
dll2 = ctypes.CDLL(str(OO2))
func = dll2.OodleLZ_Decompress
func.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                 ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                 ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
func.restype = ctypes.c_int

out = (ctypes.c_uint8 * blk0.uncompressed_size)()
for skip, label in [(0, 'full'), (6, 'skip6')]:
    src_view = (ctypes.c_uint8 * (len(compressed) - skip)).from_buffer_copy(bytes(compressed[skip:skip + len(compressed) - skip]))
    rc = func(ctypes.cast(src_view, ctypes.c_void_p), len(compressed) - skip,
              ctypes.cast(out, ctypes.c_void_p), blk0.uncompressed_size,
              1, 0, 0, 0, 0, 0, 0, 0, 0, 3)
    print(f'  [{label}] rc={rc}')

# === Test 3: oo2core_9_win64.dll WinDLL ===
print('\n=== TEST 3: oo2core_9_win64.dll WinDLL (StdCall) ===')
dll3 = ctypes.WinDLL(str(OO2))
func3 = dll3.OodleLZ_Decompress
func3.argtypes = func.argtypes
func3.restype = ctypes.c_int
out = (ctypes.c_uint8 * blk0.uncompressed_size)()
src_view = (ctypes.c_uint8 * len(compressed)).from_buffer_copy(bytes(compressed))
rc = func3(ctypes.cast(src_view, ctypes.c_void_p), len(compressed),
           ctypes.cast(out, ctypes.c_void_p), blk0.uncompressed_size,
           1, 0, 0, 0, 0, 0, 0, 0, 0, 3)
print(f'  rc={rc}')

# === INFO ===
print('\n=== INFO ===')
print(f'  compressed[0:16]  = {bytes(compressed[:16]).hex(" ")}')
print(f'  compressed[6:16]  = {bytes(compressed[6:16]).hex(" ")}  (after 6B skip)')
print(f'  expected uncompressed size (1<<shift) = {f3.uncompressed_size}')
print(f'  block0.uncompressed_size = {blk0.uncompressed_size}')