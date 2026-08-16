"""Final test: Oodle decompression on both Mitya and Nilou blocks."""
import sys, ctypes
from pathlib import Path

sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser

OO2 = Path(r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts\oo2core_9_win64.dll')

dll = ctypes.CDLL(str(OO2))
func = dll.OodleLZ_Decompress
func.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                 ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                 ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
func.restype = ctypes.c_int

def try_decompress(blk_path, name):
    print(f'\n=== {name} ({Path(blk_path).name}) ===')
    with open(blk_path, 'rb') as f:
        data = f.read()

    # Find all Blb\x03 bundles
    import re
    positions = [m.start() for m in re.finditer(b'Blb\x03', data)]
    print(f'  bundles in file: {len(positions)}')

    successes = 0
    failures = 0
    for pos in positions[:20]:  # First 20 bundles
        try:
            f3 = blb_parser.Blb3File(data, pos)
            if not f3.blocks:
                continue
            blk0 = f3.blocks[0]
            comp = bytearray(f3.block_data[:blk0.compressed_size])
            blb_parser.blb_decrypt(f3._hk, comp)
            out_size = blk0.uncompressed_size

            out = (ctypes.c_uint8 * out_size)()
            src_view = (ctypes.c_uint8 * len(comp)).from_buffer_copy(bytes(comp))
            rc = func(ctypes.cast(src_view, ctypes.c_void_p), len(comp),
                      ctypes.cast(out, ctypes.c_void_p), out_size,
                      1, 0, 0, 0, 0, 0, 0, 0, 0, 3)
            if rc > 0:
                successes += 1
                # Only print first 3 successes with details
                if successes <= 3:
                    out_bytes = bytes(out[:16])
                    print(f'  pos=0x{pos:08x} comp={blk0.compressed_size} uncomp={blk0.uncompressed_size} rc={rc} out_first16={out_bytes.hex(" ")}')
            else:
                failures += 1
        except Exception as e:
            failures += 1
    print(f'  Summary: {successes} OK, {failures} FAIL (out of {min(20, len(positions))})')

try_decompress(r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks\00\00514567.blk', 'Mitya')
try_decompress(r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk', 'Nilou (02050112)')