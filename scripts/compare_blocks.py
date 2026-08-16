"""Compare raw vs decrypted block data."""
import sys, os
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser

BLKS = [
    r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk',
    r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks\00\00514567.blk',
]

for blk_path in BLKS:
    if not os.path.exists(blk_path):
        print(f'SKIP: {blk_path}')
        continue
    with open(blk_path, 'rb') as f:
        data = f.read()
    f3 = blb_parser.Blb3File(data, 0)
    print(f'\n=== {os.path.basename(blk_path)} ===')
    print(f'  blocks={len(f3.blocks)}, comp_type flags={f3.blocks[0].flags:#x}' if f3.blocks else 'no blocks')
    if not f3.blocks:
        continue
    blk0 = f3.blocks[0]
    raw = bytes(f3.block_data[:blk0.compressed_size])
    print(f'  raw first 16: {raw[:16].hex(" ")}')
    if blk0.compressed_size > 6:
        dec = bytearray(raw)
        blb_parser.blb_decrypt(f3._hk, dec)
        print(f'  dec first 16: {bytes(dec[:16]).hex(" ")}')
        # Check XOR diff
        diffs = sum(1 for a, b in zip(raw, dec) if a != b)
        print(f'  raw vs dec diff count: {diffs}/{len(raw)}')
        print(f'  has 0x8C in dec? {0x8C in dec}, count={dec.count(0x8C)}')