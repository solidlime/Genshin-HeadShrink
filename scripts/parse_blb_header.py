"""Parse 02050112.blk header to confirm format + Oodle flow."""
import os, struct, sys
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_crypto as bc

p = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk'
with open(p,'rb') as f:
    magic = f.read(4)
    sz = struct.unpack('<I', f.read(4))[0]
    unk = struct.unpack('<I', f.read(4))[0]
    header = f.read(16)
    enc = f.read(sz)

print(f'magic={magic!r} blocksInfoSize={sz} unk={unk:08x}')
print(f'header (16B)={header.hex()}')
print(f'enc_size={len(enc)}, first 32B hex={enc[:32].hex()}')

# Decrypt blocksInfo
buf = bytearray(enc)
bc.decrypt(header, buf)
print(f'after decrypt first 64B: {bytes(buf[:64]).hex()}')

# Parse decrypted blocksInfo header
size = struct.unpack('<I', bytes(buf[:4]))[0]
last_uncomp = struct.unpack('<I', bytes(buf[4:8]))[0]
print(f'  size={size:08x} lastUncompressedSize={last_uncomp:08x}')
# skip 4B (line 67 reader.Position += 4)
blob_off = struct.unpack('<i', bytes(buf[12:16]))[0]
blob_sz = struct.unpack('<I', bytes(buf[16:20]))[0]
ct = bytes(buf[20:21])[0]
uncomp_shift = bytes(buf[21:22])[0]
print(f'  blobOffset={blob_off} blobSize={blob_sz} compressionType={ct} uncompShift={uncomp_shift} => uncompressedSize={1<<uncomp_shift}')

# After AlignStream (line 72: aligns to 8 bytes from start of stream)
# buf starts at 0. Reader position after reading 22 bytes is 22. Align to 8 = 24.
# So blocksInfoCount starts at offset 24.
# Actually the code reads u32 size (4) + u32 lastUncompressedSize (4) + skip 4 + i32 blobOff (4) + u32 blobSz (4) + u8 ct (1) + u8 shift (1) = 22 bytes
# AlignStream() aligns to next 8-byte boundary from start of stream → 24
blocks_info_count = struct.unpack('<i', bytes(buf[24:28]))[0]
nodes_count = struct.unpack('<i', bytes(buf[28:32]))[0]
print(f'  blocksInfoCount={blocks_info_count} nodesCount={nodes_count}')

# i64 blocksInfoOffset, nodesInfoOffset, flagInfoOffset (each 8 bytes = 24 total) starting at offset 32
blocks_info_off = struct.unpack('<q', bytes(buf[32:40]))[0]
nodes_info_off = struct.unpack('<q', bytes(buf[40:48]))[0]
flag_info_off = struct.unpack('<q', bytes(buf[48:56]))[0]
print(f'  blocksInfoOffset(rel)={blocks_info_off} nodesInfoOffset(rel)={nodes_info_off} flagInfoOffset(rel)={flag_info_off}')

# Blocks start at pos + offset (i.e., from current reader position which is 56 after reading the three i64s)
blocks_rel_pos = 56 + blocks_info_off
print(f'  blocks start at absolute offset in dec buf: {blocks_rel_pos}')
# Read blocks (u32 cumulative compressed sizes)
i = blocks_rel_pos
cum = []
while i + 4 <= len(buf) and len(cum) < blocks_info_count:
    cum.append(struct.unpack('<I', bytes(buf[i:i+4]))[0])
    i += 4
print(f'  cumulative compressed sizes: {cum}')

# Convert cumulative to actual sizes
sizes = []
for j, c in enumerate(cum):
    if j == 0:
        sizes.append(c)
    else:
        sizes.append(c - cum[j-1])
print(f'  per-block compressed sizes: {sizes}')

# The actual block data in the file is AFTER the encrypted blocksInfo header
# File layout: [4 magic][4 size][4 unk][16 header][blocksInfo (sz bytes)][blocks data]
# So block data starts at file offset 28 + sz
block_data_file_off = 28 + sz
print(f'  block data starts at file offset: {block_data_file_off:08x}')

# Find the end of the file (file is 52420396 bytes)
file_size = os.path.getsize(p)
print(f'  file size: {file_size}')
print(f'  remaining after header: {file_size - block_data_file_off} bytes')

# Save info
print()
print('=== SUMMARY ===')
print(f'compressionType={ct} (= 9 means Oodle in BlbFile.cs L158)')
print(f'Block 0 compressed size: {sizes[0] if sizes else "N/A"} bytes')
print(f'Last block uncompressedSize: {last_uncomp}')