"""Try forcing LZ4 and various decryption scopes."""
import sys
sys.path.insert(0, r"G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts")
from blb_parser import Blb3File
import lz4.block

BLK = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
blb = Blb3File(BLK)
blk = blb.blocks[0]

compressed = bytearray(blb.block_data[:blk.compressed_size])
print(f"first byte raw: 0x{compressed[0]:02x}")

# Try: just first byte interpreted as LZ4 token
# 0x9f -> high 9 (literals), low f (match) - valid LZ4 token!
# But Python lz4 needs correct uncompressed_size

# Try with various sizes
for sz in [262144, 262145, 262143, 524288, 131072, 65536]:
    try:
        out = lz4.block.decompress(bytes(compressed), uncompressed_size=sz)
        print(f"  uncomp={sz}: OK, got {len(out)}")
    except Exception as e:
        err = str(e)[:60]
        # only print short errors
        if 'Error code: 0' in err or 'No error' in err:
            print(f"  uncomp={sz}: {err}")
        # else silent

# Maybe full data needs more decryption beyond 128 bytes
# Re-decrypt with custom scope
import sys
sys.path.insert(0, r"G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts")
from blb_crypto import decrypt as blb_decrypt

# Check: what does the data look like past 128 bytes?
print(f"\nraw bytes 0x80-0x90 (around boundary):")
for off in range(0x80, 0x100, 16):
    row = bytes(compressed[off:off+16])
    hexs = " ".join(f"{b:02x}" for b in row)
    ascs = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
    print(f"  {off:08x}  {hexs}  {ascs}")

# Try: apply Decrypt with scope = 256 bytes (extend manually)
buf256 = bytearray(blb.block_data[:blk.compressed_size])
# First 128 bytes: standard Decrypt
blb_decrypt(blb._hk, buf256[:128])  # only first 128
# Then check if bytes 128+ also need decrypting
# Compare raw bytes 128+ with what we'd get if extended Decrypt
# For now, just see what's at byte 128
print(f"\nbyte at offset 0x80 (128): 0x{buf256[0x80]:02x}")
print(f"byte at offset 0x7F (127): 0x{buf256[0x7F]:02x}")
print(f"bytes 0x80..0x90 after standard Decrypt:")
for off in range(0x80, 0x90):
    print(f"  {off:#x}: 0x{buf256[off]:02x}")
