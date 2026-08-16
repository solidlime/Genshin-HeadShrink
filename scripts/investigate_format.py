"""Investigate decompressed bundle format and find Nilou's Mesh data."""
import sys, ctypes, struct
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

def decompress_block(f3):
    blk0 = f3.blocks[0]
    comp = bytearray(f3.block_data[:blk0.compressed_size])
    blb_parser.blb_decrypt(f3._hk, comp)
    out = (ctypes.c_uint8 * blk0.uncompressed_size)()
    src = (ctypes.c_uint8 * len(comp)).from_buffer_copy(bytes(comp))
    rc = func(ctypes.cast(src, ctypes.c_void_p), len(comp),
              ctypes.cast(out, ctypes.c_void_p), blk0.uncompressed_size,
              1, 0, 0, 0, 0, 0, 0, 0, 0, 3)
    return bytes(out[:rc]) if rc > 0 else None

def oodle_decompress_multi(f3):
    """Decompress ALL blocks in a bundle."""
    out = bytearray()
    offset = 0
    for i, blk in enumerate(f3.blocks):
        comp = bytearray(f3.block_data[offset:offset + blk.compressed_size])
        offset += blk.compressed_size
        if blk.compressed_size > 6:
            blb_parser.blb_decrypt(f3._hk, comp)
        comp_bytes = bytes(comp)
        decomp_size = blk.uncompressed_size
        if blk.flags == blb_parser.COMP_NONE:
            out += comp_bytes[:decomp_size]
            continue
        if blk.flags in (blb_parser.COMP_LZ4, blb_parser.COMP_LZ4HC):
            out += lz4.block.decompress(comp_bytes, uncompressed_size=decomp_size)
            continue
        if blk.flags == blb_parser.COMP_OODLE:
            buf = (ctypes.c_uint8 * decomp_size)()
            src = (ctypes.c_uint8 * len(comp_bytes)).from_buffer_copy(comp_bytes)
            rc = func(ctypes.cast(src, ctypes.c_void_p), len(comp_bytes),
                      ctypes.cast(buf, ctypes.c_void_p), decomp_size,
                      1, 0, 0, 0, 0, 0, 0, 0, 0, 3)
            if rc > 0:
                out += bytes(buf[:rc])
            else:
                return None
    return bytes(out)

import lz4.block

# Test on Mitya first (known good)
print('=== Mitya 00514567.blk, first bundle ===')
BLK_MITYA = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks\00\00514567.blk'
with open(BLK_MITYA, 'rb') as f:
    data = f.read()
import re
positions = [m.start() for m in re.finditer(b'Blb\x03', data)]
f3 = blb_parser.Blb3File(data, positions[0])
print(f'blocks: {len(f3.blocks)}')
out_data = oodle_decompress_multi(f3)
print(f'decompressed total: {len(out_data)} bytes')
print(f'first 64 bytes: {out_data[:64].hex(" ")}')

# Look for Unity magic strings
for magic in [b'UnityFS', b'UnityRaw', b'UnityWeb', b'Unity', b'TypeTree', b'CAB-', b'mdb', b'MDB']:
    if magic in out_data:
        idx = out_data.find(magic)
        print(f'Found magic "{magic.decode()}" at offset {idx}: ...{out_data[idx:idx+32].hex(" ")}')

# Look for "m_Name" string (Unity asset name)
for name_str in [b'Body', b'Face', b'Bang', b'Mitya', b'Nilou', b'Mesh', b'Avatar']:
    if name_str in out_data:
        idx = out_data.find(name_str)
        ctx = out_data[max(0,idx-8):idx+32]
        print(f'Found "{name_str.decode()}" at offset {idx}: ctx={ctx.hex(" ")}')