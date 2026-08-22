"""Dump raw header fields to debug misalignment."""
import sys, struct
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')

BLKS = [
    r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk',
    r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks\00\00514567.blk',
]

for p in BLKS:
    with open(p, 'rb') as f:
        data = f.read()
    print(f'\n=== {p.rsplit(chr(92), 1)[-1]} ===')
    # header
    print(f'  magic: {data[0:4].hex()}')
    bisize = struct.unpack('<I', data[4:8])[0]
    print(f'  blocksInfoSize: {bisize}')
    unk = struct.unpack('<I', data[8:12])[0]
    print(f'  unk: {unk:#x}')
    hk = data[12:28]
    print(f'  headerKey: {hk.hex()}')

    # encrypted blocksInfo
    bi = bytearray(data[28:28+bisize])
    print(f'  encrypted bi first 16: {bytes(bi[:16]).hex(" ")}')

    # Try decrypting and check if result is valid (has u32 size at start)
    import blb_parser
    blb_parser.blb_decrypt(bytes(hk), bi)
    print(f'  decrypted bi first 32: {bytes(bi[:32]).hex(" ")}')
    if len(bi) >= 8:
        u = struct.unpack('<II', bi[:8])
        print(f'  dec u32[0]={u[0]:,} u32[1]={u[1]:,}')
    if len(bi) >= 16:
        b2 = struct.unpack('<iI', bi[8:16])
        print(f'  dec i32={b2[0]:,} u32={b2[1]:,}')
    if len(bi) >= 20:
        ct = bi[16]
        us = bi[17]
        print(f'  comp_type={ct} uncomp_shift={us} (1<<us={1<<us})')