"""Try different XOR strategies to find LZ4/Zstd/Unity magics."""
import struct

PATH = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
with open(PATH, "rb") as f:
    data = f.read()

key = data[0x0C:0x1C]
LZ4 = b"\x04\x22\x4d\x18"
ZSTD = b"\x28\xb5\x2f\xfd"
UFS = b"UnityFS\x00"

def search(blob, label):
    hits = []
    for i in range(len(blob) - 3):
        w = bytes(blob[i:i+4])
        if w == LZ4:
            hits.append((i, "LZ4", w.hex()))
        elif w == ZSTD:
            hits.append((i, "ZSTD", w.hex()))
        if i + 7 <= len(blob) and bytes(blob[i:i+7]) == UFS:
            hits.append((i, "UFS", bytes(blob[i:i+16]).hex()))
    print(f"{label}: {len(hits)} hits")
    for h in hits[:5]:
        print(f"  @{h[0]:#x}  {h[1]}  {h[2]}")
    return hits

# Try: per-block XOR with key, blocks at various offsets
# Also try: key starts fresh at each "block" boundary

# Hypothesis 1: header = 0x1C bytes plaintext, then XOR'd data
# Look at 0x1C+ with XOR repeating
buf = bytearray(data)
for i in range(0x1C, len(buf), 16):
    for j in range(16):
        if i+j < len(buf):
            buf[i+j] ^= key[j]
search(buf, "XOR from 0x1C, repeating key")

# Hypothesis 2: 0x1C is start of first block; key resets per-block
# Need to know block boundaries — guess 10MB each
buf = bytearray(data)
def xor_per_block(buf, start, key, block_size=10*1024*1024):
    end = len(buf)
    pos = start
    while pos < end:
        n = min(block_size, end - pos)
        for i in range(n):
            buf[pos+i] ^= key[i % 16]
        pos += n
for bs in [10*1024*1024, 5*1024*1024, 20*1024*1024, 12*1024*1024]:
    b = bytearray(data)
    xor_per_block(b, 0x1C, key, bs)
    h = search(b, f"per-block XOR, block_size={bs}")
    if h:
        print(f"  ^^ FOUND with block_size={bs}")
        break
