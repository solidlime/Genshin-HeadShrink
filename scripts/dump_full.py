"""Definitive dump of bi structure with byte offsets."""
import sys, struct
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser

BLK = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk'

with open(BLK, 'rb') as f:
    data = f.read()

# Use parser
f3 = blb_parser.Blb3File(data, 0)
print(f'Parser says:')
print(f'  uncompressed_size (size field) = {f3.uncompressed_size}')
print(f'  blocks_info_count = {len(f3.blocks)}')
print(f'  block0.compressed_size = {f3.blocks[0].compressed_size}')
print(f'  block0.uncompressed_size = {f3.blocks[0].uncompressed_size}')
print(f'  block0.flags = 0x{f3.blocks[0].flags:x}')
print(f'  block_data_offset = 0x{f3.block_data_offset:x}')

# Manual parse
print(f'\nManual parse:')
bisize = struct.unpack('<I', data[4:8])[0]
print(f'  bisize = {bisize}')
hk = data[12:28]
print(f'  hk = {hk.hex()}')

# Decrypt bi
bi = bytearray(data[28:28+bisize])
blb_parser.blb_decrypt(hk, bi)

# Print bi bytes with offsets
print(f'\nDecrypted blocksInfo ({len(bi)} bytes):')
for off in range(0, min(len(bi), 64), 4):
    if off + 4 <= len(bi):
        v = struct.unpack('<I', bi[off:off+4])[0]
        print(f'  [{off:2d}] u32 LE = {v} (0x{v:08x})')
    elif off + 2 <= len(bi):
        v = struct.unpack('<H', bi[off:off+2])[0]
        print(f'  [{off:2d}] u16 LE = {v}')

# Print key fields
print(f'\nKey field values:')
print(f'  size (offset 0): {struct.unpack("<I", bi[0:4])[0]}')
print(f'  lastUncompressedSize (offset 4): {struct.unpack("<I", bi[4:8])[0]}')
print(f'  padding (offset 8): {struct.unpack("<I", bi[8:12])[0]}')
print(f'  blobOff (offset 12): {struct.unpack("<i", bi[12:16])[0]}')
print(f'  blobSize (offset 16): {struct.unpack("<I", bi[16:20])[0]}')
print(f'  comp_type (offset 20): {bi[20]}')
print(f'  shift (offset 21): {bi[21]}')
print(f'  align (offset 22-23): {bi[22]:02x} {bi[23]:02x}')
print(f'  blocksInfoCount (offset 24): {struct.unpack("<i", bi[24:28])[0]}')
print(f'  nodesCount (offset 28): {struct.unpack("<i", bi[28:32])[0]}')
print(f'  blocksInfoOff (offset 32): {struct.unpack("<q", bi[32:40])[0]}')
print(f'  nodesInfoOff (offset 40): {struct.unpack("<q", bi[40:48])[0]}')
print(f'  flagInfoOff (offset 48): {struct.unpack("<q", bi[48:56])[0]}')

# block_data location
block_data_off_expected = 28 + bisize
print(f'\nBlock data offset (28 + bisize): 0x{block_data_off_expected:x}')
print(f'Actual block_data_offset from parser: 0x{f3.block_data_offset:x}')

# Print block_data first bytes
print(f'\nblock_data[0:32]: {f3.block_data[:32].hex(" ")}')