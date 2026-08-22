"""Try LZ4 decompression on Mitya + Nilou to see if comp_type=9 is misleading."""
import sys
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser
import lz4.block

BLKS = [
    (r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk', '02050112'),
    (r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks\00\00514567.blk', 'Mitya'),
]

for blk_path, name in BLKS:
    with open(blk_path, 'rb') as f:
        data = f.read()
    f3 = blb_parser.Blb3File(data, 0)
    blk0 = f3.blocks[0]
    print(f'\n=== {name} (flags=0x{blk0.flags:x}, comp={blk0.compressed_size}, uncomp={blk0.uncompressed_size}) ===')

    # Decrypt block 0
    comp = bytearray(f3.block_data[:blk0.compressed_size])
    blb_parser.blb_decrypt(f3._hk, comp)
    dec_bytes = bytes(comp)

    # Try LZ4
    for u in (blk0.uncompressed_size, 1 << 18, 1 << 16, 1 << 20, 1 << 24):
        try:
            d = lz4.block.decompress(dec_bytes, uncompressed_size=u)
            print(f'  LZ4 OK at size={u}: {len(d)} bytes, first16={d[:16].hex(" ")}')
            break
        except Exception as e:
            pass

    # Try LZ4 on RAW (no decrypt)
    raw = bytes(f3.block_data[:blk0.compressed_size])
    for u in (blk0.uncompressed_size, 1 << 18, 1 << 16):
        try:
            d = lz4.block.decompress(raw, uncompressed_size=u)
            print(f'  LZ4 RAW OK at size={u}: {len(d)} bytes, first16={d[:16].hex(" ")}')
            break
        except Exception as e:
            pass

    # Try LZ4 with header-store=true
    try:
        d = lz4.block.decompress(dec_bytes, uncompressed_size=blk0.uncompressed_size, store_size=False)
        print(f'  LZ4 store_size=False: {len(d)} bytes')
    except Exception as e:
        print(f'  LZ4 store_size=False: {str(e)[:80]}')

    # Try LZ4 frame format
    try:
        import lz4.frame
        d = lz4.frame.decompress(dec_bytes)
        print(f'  LZ4 frame: {len(d)} bytes')
    except Exception as e:
        print(f'  LZ4 frame: {str(e)[:80]}')