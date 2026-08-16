"""Oodle test with correct uncompressedSize=262144 (1<<shift)."""
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
print(f'block0: comp={blk0.compressed_size} flags=0x{blk0.flags:x}')

# Read raw + decrypt
compressed = bytearray(f3.block_data[:blk0.compressed_size])
blb_parser.blb_decrypt(f3._hk, compressed)
print(f'dec first 16: {bytes(compressed[:16]).hex(" ")}')

# Correct uncompressedSize: 1 << shift
# Read shift from decrypted blocksInfo: bi[21]
import struct
bisize = struct.unpack('<I', data[4:8])[0]
bi = bytearray(data[28:28+bisize])
blb_parser.blb_decrypt(f3._hk, bi)
shift = bi[21]
correct_uncomp = 1 << shift
print(f'shift={shift} correct_uncompressedSize={correct_uncomp}')

# Test 1: OOZ with correct size
print('\n=== TEST 1: OOZ with size=262144 ===')
ooz = ctypes.WinDLL(str(OOZ))
ooz.Ooz_Decompress.restype = ctypes.c_int
# Discover argcount first
try:
    func = ooz.Ooz_Decompress
    print(f'OOZ_Ooz_Decompress exported')
except AttributeError:
    print('Ooz_Decompress NOT FOUND')
    raise

# Try 15 args - 13 from argtypes in oodle.py + 2 extras (decMemSize + threadPhase order?)
argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
func.argtypes = argtypes
func.restype = ctypes.c_int

out = (ctypes.c_uint8 * correct_uncomp)()
src = (ctypes.c_uint8 * len(compressed)).from_buffer_copy(bytes(compressed))
rc = func(ctypes.cast(src, ctypes.c_void_p), len(compressed),
          ctypes.cast(out, ctypes.c_void_p), correct_uncomp,
          1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3)
print(f'OOZ rc={rc}')
if rc > 0:
    print(f'  out first 16: {bytes(out[:16]).hex(" ")}')
print(f'  rc={rc} (positive=bytes written, 0=fail)')
if rc > 0:
    print(f'  out first 16: {bytes(out[:16]).hex(" ")}')

# Test 2: oo2core with correct size
print('\n=== TEST 2: oo2core (CDLL) with size=262144 ===')
dll = ctypes.CDLL(str(OO2))
f = dll.OodleLZ_Decompress
f.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
f.restype = ctypes.c_int
out = (ctypes.c_uint8 * correct_uncomp)()
rc = f(ctypes.cast(src, ctypes.c_void_p), len(compressed),
       ctypes.cast(out, ctypes.c_void_p), correct_uncomp,
       1, 0, 0, 0, 0, 0, 0, 0, 0, 3)
print(f'  rc={rc}')
if rc > 0:
    print(f'  out first 16: {bytes(out[:16]).hex(" ")}')

# Test 3: oo2core with skip 6 bytes
print('\n=== TEST 3: oo2core skip6 with size=262144 ===')
out = (ctypes.c_uint8 * correct_uncomp)()
src_skip = (ctypes.c_uint8 * (len(compressed) - 6)).from_buffer_copy(bytes(compressed[6:]))
rc = f(ctypes.cast(src_skip, ctypes.c_void_p), len(compressed) - 6,
       ctypes.cast(out, ctypes.c_void_p), correct_uncomp,
       1, 0, 0, 0, 0, 0, 0, 0, 0, 3)
print(f'  rc={rc}')

# Test 4: Mitya 00514567.blk
print('\n=== TEST 4: Mitya 00514567.blk ===')
BLK2 = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks\00\00514567.blk'
with open(BLK2, 'rb') as f:
    d2 = f.read()
f3m = blb_parser.Blb3File(d2, 0)
bism = struct.unpack('<I', d2[4:8])[0]
bim = bytearray(d2[28:28+bism])
blb_parser.blb_decrypt(f3m._hk, bim)
shift_m = bim[21]
uncomp_m = 1 << shift_m
print(f'Mitya shift={shift_m} uncomp_size={uncomp_m}')
blkm = f3m.blocks[0]
print(f'Mitya block0: comp={blkm.compressed_size} flags=0x{blkm.flags:x}')
comp_m = bytearray(f3m.block_data[:blkm.compressed_size])
blb_parser.blb_decrypt(f3m._hk, comp_m)
print(f'Mitya dec first 16: {bytes(comp_m[:16]).hex(" ")}')
out = (ctypes.c_uint8 * uncomp_m)()
src_m = (ctypes.c_uint8 * len(comp_m)).from_buffer_copy(bytes(comp_m))
rc = dll.OodleLZ_Decompress(ctypes.cast(src_m, ctypes.c_void_p), len(comp_m),
                            ctypes.cast(out, ctypes.c_void_p), uncomp_m,
                            1, 0, 0, 0, 0, 0, 0, 0, 0, 3)
print(f'Mitya oo2core rc={rc}')
if rc > 0:
    print(f'  out first 16: {bytes(out[:16]).hex(" ")}')