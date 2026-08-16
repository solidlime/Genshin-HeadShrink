"""Blb header inspector. Read-only, prints structure."""
import struct, sys

PATH = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"

with open(PATH, "rb") as f:
    data = f.read()

print(f"file size: {len(data):,} bytes")

magic = data[0:3]
print(f"magic @0x00: {magic!r} (expect b'Blb')")

ver = data[3]
print(f"version @0x03: 0x{ver:02x}")

size = struct.unpack(">I", data[4:8])[0]
print(f"size @0x04: {size:,} (BE dword)")

block_count = struct.unpack(">I", data[8:12])[0]
print(f"blockCount @0x08: {block_count} (BE dword)")

xor_key = data[0x0C:0x1C]
print(f"xor key @0x0C..0x1B: {xor_key.hex()}")

# Dump first ~256 bytes after header
print("\n--- hex dump 0x00..0x100 ---")
for off in range(0, 0x100, 16):
    row = data[off:off+16]
    hexs = " ".join(f"{b:02x}" for b in row)
    ascs = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
    print(f"{off:08x}  {hexs:<47}  {ascs}")
