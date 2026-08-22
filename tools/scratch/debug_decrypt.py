"""Debug: extract blocksInfo, decrypt, dump bytes."""
import struct, sys
sys.path.insert(0, r"G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts")
from blb_crypto import decrypt as blb_decrypt

BLK = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
data = open(BLK, "rb").read()
size = struct.unpack("<I", data[0x04:0x08])[0]
hk = data[0x0C:0x1C]
print(f"size (LE): {size}")
print(f"hk: {hk.hex()}")

bi = bytearray(data[0x1C:0x1C + size])
print(f"encrypted blocksInfo first 32B: {bytes(bi[:32]).hex()}")

# Decrypt only the first 128 bytes (per BlbUtils.Decrypt)
blb_decrypt(hk, bi)

print(f"\ndecrypted first 64B:")
for off in range(0, 64, 16):
    row = bytes(bi[off:off+16])
    hexs = " ".join(f"{b:02x}" for b in row)
    ascs = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
    print(f"{off:08x}  {hexs:<47}  {ascs}")

# Look for any recognizable structure
print(f"\ndecrypted 0x00..0x18 as u32 LE:")
for off in range(0, 0x18, 4):
    v = struct.unpack("<I", bi[off:off+4])[0]
    print(f"  @{off:#x}: {v}")
