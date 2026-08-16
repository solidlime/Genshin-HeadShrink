"""Try multiple decompression algorithms on block 0."""
import sys, struct
sys.path.insert(0, r"G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts")
from blb_parser import Blb3File
from blb_crypto import decrypt as blb_decrypt

BLK = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
data = open(BLK, "rb").read()
b = Blb3File(data, 0)
blk = b.blocks[0]
compressed = bytearray(b.block_data[:blk.compressed_size])
blb_decrypt(b._hk, compressed)
print(f"comp={blk.compressed_size} uncomp={blk.uncompressed_size}")

# Try Zstd
try:
    import zstandard as zstd
    dctx = zstd.ZstdDecompressor()
    out = dctx.decompress(bytes(compressed), max_output_size=10*1024*1024)
    print(f"Zstd: OK size={len(out):,}")
except ImportError:
    print("Zstd: not installed")
except Exception as e:
    print(f"Zstd: {str(e)[:80]}")

# Try Zstd via builtin
import zlib
for algo_name, decompress_fn in [
    ("zlib (deflate)", lambda d: zlib.decompress(d, -15)),
    ("zlib (auto)", lambda d: zlib.decompress(d)),
]:
    try:
        out = decompress_fn(bytes(compressed[:1024]))
        print(f"{algo_name}: OK size={len(out):,}")
    except Exception as e:
        print(f"{algo_name}: {str(e)[:60]}")

# Try Brotli
try:
    import brotli
    out = brotli.decompress(bytes(compressed))
    print(f"Brotli: OK size={len(out):,}")
except ImportError:
    print("Brotli: not installed")
except Exception as e:
    print(f"Brotli: {str(e)[:60]}")

# Try LZMA
import lzma
for fmt in [lzma.FORMAT_ALONE, lzma.FORMAT_AUTO]:
    try:
        out = lzma.decompress(bytes(compressed[:1024]), format=fmt)
        print(f"LZMA ({fmt}): OK size={len(out):,}")
    except Exception as e:
        print(f"LZMA ({fmt}): {str(e)[:60]}")

# Look at first 16 bytes — what does the data start with?
print(f"\nFirst 16 bytes (post-Decrypt): {bytes(compressed[:16]).hex()}")
# UnityFS magic? "UnityFS\x00" = 55 6E 69 74 79 46 53 00
# LZ4 frame magic? 04 22 4D 18
# Zstd magic? 28 B5 2F FD
# LZMA alone header? 5D 00 00
print(f"Is 'UnityFS' magic? {compressed[:7] == bytes([0x55,0x6e,0x69,0x74,0x79,0x46,0x53])}")
