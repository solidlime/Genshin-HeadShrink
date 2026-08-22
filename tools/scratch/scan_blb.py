"""Scan .blk for LZ4/Zstd magic after XOR decryption (16-byte repeating key)."""
import struct

PATH = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
with open(PATH, "rb") as f:
    data = f.read()

key = data[0x0C:0x1C]
print(f"key: {key.hex()}")

LZ4_LE = b"\x04\x22\x4d\x18"
LZ4_BE = b"\x18\x4d\x22\x04"
ZSTD_LE = b"\x28\xb5\x2f\xfd"
ZSTD_BE = b"\xfd\x2f\xb5\x28"

# XOR each 16-byte block with key
decoded = bytearray(len(data))
for i in range(0, len(data), 16):
    chunk = data[i:i+16]
    k = key[:len(chunk)]
    decoded[i:i+len(chunk)] = bytes(c ^ kk for c, kk in zip(chunk, k))

# Search for magic
hits = []
for i in range(len(decoded) - 3):
    w = bytes(decoded[i:i+4])
    if w in (LZ4_LE, LZ4_BE, ZSTD_LE, ZSTD_BE):
        hits.append((i, w.hex()))

print(f"hits: {len(hits)}")
for h in hits[:20]:
    print(f"  @{h[0]:#x}  {h[1]}")

# Also check if header area (0x1C+) has recognizable patterns after XOR
print("\n--- decoded 0x1C..0xC0 (first 5 blocks table?) ---")
for off in range(0x1C, 0xC0, 16):
    row = decoded[off:off+16]
    hexs = " ".join(f"{b:02x}" for b in row)
    ascs = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
    print(f"{off:08x}  {hexs:<47}  {ascs}")
