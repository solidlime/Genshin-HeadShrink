"""Search for additional Blb\x03 magic occurrences."""
import struct

BLK = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\01535869.blk"
data = open(BLK, "rb").read()
print(f"file size: {len(data):,}")

magic = b"Blb\x03"
positions = []
i = 0
while True:
    j = data.find(magic, i)
    if j < 0: break
    positions.append(j)
    i = j + 1

print(f"Blb\\x03 occurrences: {len(positions)}")
for p in positions:
    size = struct.unpack("<I", data[p+4:p+8])[0]
    print(f"  @{p:#x}  blocksInfoSize={size}")
