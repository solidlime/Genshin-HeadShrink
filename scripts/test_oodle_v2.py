"""Extract and decompress Block 0 from 02050112.blk using Oodle."""
import ctypes, struct, sys, os

p = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk'

# Parse header
with open(p,'rb') as f:
    f.read(4)  # magic
    sz = struct.unpack('<I', f.read(4))[0]
    f.read(4)   # unk
    header = bytearray(f.read(16))
    enc = bytearray(f.read(sz))
    block0_raw = bytearray(f.read(61708))   # 61708 bytes confirmed from parse_blb_header.py

print(f'header={bytes(header).hex()}')
print(f'block0_raw first 16B={bytes(block0_raw[:16]).hex()}')

# Decrypt first 16B using BlbUtils.Decrypt = our 4-step decrypt
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_crypto as bc
bc.decrypt(bytes(header), block0_raw)
print(f'after decrypt first 16B={bytes(block0_raw[:16]).hex()}')
print(f'first 6 bytes (Oodle header skip): {bytes(block0_raw[:6]).hex()}')

# Test 1: Ooz_Decompress (AnimeStudio.Ooz.dll, StdCall)
print('\n=== TEST 1: AnimeStudio.Ooz.dll Ooz_Decompress ===')
try:
    ooz_path = r'D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\AnimeStudio.Ooz.dll'
    dll = ctypes.WinDLL(ooz_path)
    OOZ_Decompress = dll.Ooz_Decompress
    OOZ_Decompress.argtypes = [
        ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int,
        ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int
    ]
    OOZ_Decompress.restype = ctypes.c_int
    out = (ctypes.c_ubyte * 124036)()
    n = OOZ_Decompress(
        (ctypes.c_ubyte * len(block0_raw)).from_buffer(block0_raw), len(block0_raw),
        out, 124036,
        1, 0, 0,    # fuzzSafe, checkCRC, verbosity
        0, 0, 0, 0, 0, 0,  # rawBuffer, fpCallback, callbackUserData, decoderMemory, decoderMemorySize
        3            # threadPhase
    )
    print(f'Ooz_Decompress returned: {n}')
except Exception as e:
    print(f'Ooz failed: {e}')

# Test 2: OodleLZ_Decompress (oo2core_9_win64.dll, Cdecl)
print('\n=== TEST 2: oo2core_9_win64.dll OodleLZ_Decompress ===')
try:
    oo2_path = r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts\oo2core_9_win64.dll'
    if not os.path.exists(oo2_path):
        print(f'{oo2_path} not found')
    else:
        dll = ctypes.CDLL(oo2_path)
        OodleLZ_Decompress = dll.OodleLZ_Decompress
        OodleLZ_Decompress.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int
        ]
        OodleLZ_Decompress.restype = ctypes.c_int
        out2 = (ctypes.c_ubyte * 124036)()
        n = OodleLZ_Decompress(
            (ctypes.c_ubyte * len(block0_raw)).from_buffer(block0_raw), len(block0_raw),
            out2, 124036,
            1, 0, 0,    # fuzzSafe, checkCRC, verbosity
            0, 0, 0, 0, 0, 0,
            3
        )
        print(f'OodleLZ_Decompress returned: {n}')
except Exception as e:
    print(f'OodleLZ failed: {e}')

# Test 3: Same as test 2 but skip first 6 bytes (Oodle header)
print('\n=== TEST 3: OodleLZ_Decompress with 6-byte header skipped ===')
try:
    oo2_path = r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts\oo2core_9_win64.dll'
    dll = ctypes.CDLL(oo2_path)
    OodleLZ_Decompress = dll.OodleLZ_Decompress
    OodleLZ_Decompress.argtypes = [
        ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int,
        ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int
    ]
    OodleLZ_Decompress.restype = ctypes.c_int
    payload = bytes(block0_raw[6:])   # skip 6-byte header
    print(f'payload size: {len(payload)} bytes (after 6B skip)')
    out3 = (ctypes.c_ubyte * 124036)()
    n = OodleLZ_Decompress(
        (ctypes.c_ubyte * len(payload)).from_buffer(payload), len(payload),
        out3, 124036,
        1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3
    )
    print(f'OodleLZ_Decompress (6B skipped) returned: {n}')
except Exception as e:
    print(f'OodleLZ (6B skip) failed: {e}')