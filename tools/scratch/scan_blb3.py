"""Try more XOR strategies: per-block with rolling key, byte-counter XOR, RC4."""
import struct

PATH = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
with open(PATH, "rb") as f:
    data = f.read()

key = data[0x0C:0x1C]

LZ4 = b"\x04\x22\x4d\x18"
ZSTD = b"\x28\xb5\x2f\xfd"
UFS = b"UnityFS\x00"

def search(blob, label, max_hits=3):
    hits = []
    for i in range(len(blob) - 3):
        w = bytes(blob[i:i+4])
        if w == LZ4:
            hits.append((i, "LZ4"))
        elif w == ZSTD:
            hits.append((i, "ZSTD"))
        if i + 7 <= len(blob) and bytes(blob[i:i+7]) == UFS:
            hits.append((i, "UFS"))
    print(f"{label}: {len(hits)} hits", end="")
    for h in hits[:max_hits]:
        print(f"  @{h[0]:#x}({h[1]})", end="")
    print()
    return hits

# Strategy A: XOR with rolling counter (key[i] + (i >> 4))
# Strategy B: XOR with byte position added to key
# Strategy C: XOR with key shifted by header bytes
# Strategy D: Look at the structure differently - maybe XOR is applied AFTER decompression

# Actually, let me also try: the XOR key might not apply to block table.
# Structure: header (28 bytes plaintext) | block table (XOR'd) | block data (XOR'd)
# Or: header (28 bytes plaintext) | first 5 entries are sizes, NOT XOR'd | blocks are XOR'd

# What if the entries are 8-byte (compressed_size, offset) BE pairs?
# Reading 5 entries from 0x1C (8 bytes each):
# Entry 0: 90 1c 9b 10 a6 04 d6 eb
#   BE: offset=0x109b1c90=278481040, size=0xebd604a6=3957043878
# Entry 1: 15 fb 4a 35 b4 69 43 f2
#   BE: offset=0x354afb15=894235413, size=0xf24369b4=4064786356

# What about LE? Bytes 90 1c 9b 10 LE = 0x109b1c90 same as BE due to byte order, no:
# Actually 90 1c 9b 10 LE = 0x109b1c90, BE = 0x901c9b10
# Let me try LE:
for off in range(0x1C, 0x6C, 16):
    chunk = data[off:off+8]
    val_be = struct.unpack(">Q", chunk)[0]
    val_le = struct.unpack("<Q", chunk)[0]
    print(f"@{off:#x}: BE={val_be:>20,}  LE={val_le:>20,}")

# What if entries are 4-byte and there's 5 of them (20 bytes), then 12 bytes of something else?
# 0x1C-0x2F would be 5 entries of 4 bytes
# But 5 entries * 4 bytes = 20 bytes, ends at 0x30
# Let me try: 0x1C-0x30 are 5 single-dword entries
print("\n--- 4-byte entries ---")
for off in range(0x1C, 0x30, 4):
    val_be = struct.unpack(">I", data[off:off+4])[0]
    val_le = struct.unpack("<I", data[off:off+4])[0]
    print(f"@{off:#x}: BE={val_be:>10,}  LE={val_le:>10,}")
