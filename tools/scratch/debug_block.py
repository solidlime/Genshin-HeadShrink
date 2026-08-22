"""Debug block 0 decryption + LZ4 attempt."""
import sys
sys.path.insert(0, r"G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts")
from blb_parser import Blb3File
import lz4.block

BLK = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
blb = Blb3File(BLK)
blk = blb.blocks[0]
print(f"block[0]: comp={blk.compressed_size}, uncomp={blk.uncompressed_size}, flags=0x{blk.flags:x}")

start = 0  # block[0] starts at 0
compressed = bytearray(blb.block_data[start:start + blk.compressed_size])
print(f"\nraw first 32B: {bytes(compressed[:32]).hex()}")

# Apply Decrypt
from blb_crypto import decrypt as blb_decrypt
blb_decrypt(blb._hk, compressed)
print(f"decrypted first 64B:")
for off in range(0, 64, 16):
    row = bytes(compressed[off:off+16])
    hexs = " ".join(f"{b:02x}" for b in row)
    ascs = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
    print(f"{off:08x}  {hexs:<47}  {ascs}")

# Look for known compression magics
LZ4_MAGIC = b"\x04\x22\x4d\x18"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
LZMA_PROP = b"\x5d\x00\x00"

for magic, name in [(LZ4_MAGIC, "LZ4"), (ZSTD_MAGIC, "ZSTD"), (LZMA_PROP, "LZMA")]:
    idx = compressed.find(magic)
    print(f"  {name} magic in first 1024B: idx={idx}")

# Try LZ4 with different params
print("\nTrying LZ4 decompression:")
try:
    out = lz4.block.decompress(bytes(compressed), uncompressed_size=blk.uncompressed_size)
    print(f"  OK, size={len(out)}")
except Exception as e:
    print(f"  with size: {e!r}")
try:
    out = lz4.block.decompress(bytes(compressed))
    print(f"  no size: OK, size={len(out)}")
except Exception as e:
    print(f"  no size: {e!r}")

# Try with bigger uncomp size (in case it's wrong)
for size_try in [262144, 262145, 524288, 1048576]:
    try:
        out = lz4.block.decompress(bytes(compressed), uncompressed_size=size_try)
        print(f"  size={size_try}: OK, decompressed={len(out)}")
    except Exception as e:
        pass
