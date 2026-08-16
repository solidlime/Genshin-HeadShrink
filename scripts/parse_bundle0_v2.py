"""Parse bundle 0 of 02050112.blk as Unity CAB.

Unity SerializedFile header (m_Version >= 22):
  string m_Header (length-prefixed)
  u32 m_FileSize
  u32 m_Version
  u32 m_DataOffset
  u8  m_Endianess
  u8[3] m_Reserved

After header:
  u8 m_IsBigIDFlag (only if m_Version >= 22)
  if big: u64 m_ObjectCount, m_Objects; else u32 m_ObjectCount, m_Objects
  if m_Version >= 22: i64 pathID stored as int64

For typeID/version pairs:
  for each object:
    if big: u64 pathID, then i32 byteStart, i32 byteSize, i32 typeID
    ...
  u32 m_TypeCount
  for each type:
    i32 classID (or u32 in some versions)
    u16 m_IsStrippedType
    i16 m_ScriptTypeIndex
    if m_Version >= 21:
      if m_Version >= 17: i64 m_ScriptID (hash)
      if stripped: SerializedTypeReference m_ScriptType
    if m_Version >= 21: m_Typetree (depending on flags)
"""

import struct
import sys
import os

# Quick test: open 02050112.blk and decompress bundle 0
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
from blb_parser import Blb3File
from blb_crypto import HEADER_KEY

BLK_PATH = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk'

print(f"[load] {BLK_PATH}")
f = Blb3File(BLK_PATH)
print(f"[load] bundles: {len(f.bundles)}")

# Get first bundle
b0 = f.bundles[0]
print(f"[bundle0] blocks: {len(b0.blocks)}, nodes: {len(b0.nodes)}")
for blk in b0.blocks:
    print(f"  block: comp={blk.compressed_size} uncomp={blk.uncompressed_size} type={blk.compression_type}")

# Decompress bundle 0 block 0
import lz4.block
from oodle import oodle_decompress

# Get block 0 raw bytes
reader = open(BLK_PATH, 'rb')

# Find the actual file offset for block 0 (after header + blocksInfo)
# Use the bundles/blocks info to locate it
print(f"[info] blocksInfo size from header: {f._blocks_info_size}")
print(f"[info] Header key: {f._header.hex()}")

# Try to locate block 0 data
# header: 4 (magic) + 4 (size) + 4 (unk) + 16 (key) = 28 bytes
# then blocksInfoSize bytes of encrypted blocksInfo
# then the rest is block data

# Read blocksInfo
reader.seek(28)
encrypted_blocks_info = reader.read(f._blocks_info_size)
# Decrypt blocksInfo
from blb_crypto import blb_decrypt
decrypted_bi = bytearray(encrypted_blocks_info)
blb_decrypt(f._header, decrypted_bi)
print(f"[bi] decrypted first 64 bytes: {decrypted_bi[:64].hex()}")

# Parse decrypted blocksInfo
# After decrypt: 4B size, 4B lastUncompressedSize, 4B padding, 4B blobOffset, 4B blobSize, 1B comp, 1B uncompShift, padding, then nodes structure
# Actually the structure is:
#   u32 size
#   u32 lastUncompressedSize
#   u32 padding
#   i32 blobOffset
#   u32 blobSize
#   u8  compressionType
#   u8  uncompShift (log2 of uncompSize)
#   align (8 bytes total for these last 2)
# Then:
#   i32 blocksInfoCount
#   i32 nodesCount
#   i64 blocksInfoOff
#   i64 nodesInfoOff
#   i64 flagInfoOff

size, last_uncomp_size = struct.unpack_from('<II', decrypted_bi, 0)
print(f"[bi] size={size}, lastUncompressedSize={last_uncomp_size}")

# Skip padding (4 bytes)
off = 12
blob_offset, blob_size = struct.unpack_from('<iI', decrypted_bi, off)
off += 8
comp_type = struct.unpack_from('<B', decrypted_bi, off)[0]
off += 1
uncomp_shift = struct.unpack_from('<B', decrypted_bi, off)[0]
off += 1
# 8-byte align
if off % 8 != 0:
    off += 8 - (off % 8)
print(f"[bi] blobOffset={blob_offset}, blobSize={blob_size}, compType={comp_type}, uncompShift={uncomp_shift}")
uncomp_size = 1 << uncomp_shift
print(f"[bi] uncompressedSize = {uncomp_size}")

blocks_info_count, nodes_count = struct.unpack_from('<ii', decrypted_bi, off)
off += 8
blocks_info_off, nodes_info_off, flag_info_off = struct.unpack_from('<qqq', decrypted_bi, off)
off += 24
print(f"[bi] blocksInfoCount={blocks_info_count}, nodesCount={nodes_count}")
print(f"[bi] blocksInfoOff={blocks_info_off}, nodesInfoOff={nodes_info_off}, flagInfoOff={flag_info_off}")

# Now locate block data: blocksInfo ends at offset 28 + blocksInfoSize in file
# Block data starts at blocksInfoOff (relative to start of decrypted bundle data, which is at file offset 28 + blocksInfoSize)
file_blocks_data_start = 28 + f._blocks_info_size
print(f"[file] block data starts at {file_blocks_data_start}")

# Read the compressed block
reader.seek(file_blocks_data_start)
compressed_block = reader.read(blob_size)
print(f"[block] compressed bytes: {len(compressed_block)} (expected {blob_size})")
print(f"[block] first 16 bytes: {compressed_block[:16].hex()}")

# Decrypt if needed (block data is also 4-step encrypted for non-None/LZMA types)
if comp_type == 9:  # Oodle
    decrypted_block = bytearray(compressed_block)
    blb_decrypt(f._header, decrypted_block)
    print(f"[block] decrypted first 16 bytes: {decrypted_block[:16].hex()}")
    # Skip 6-byte Oodle header
    oodle_payload = bytes(decrypted_block[6:])
    print(f"[block] oodle payload first 16: {oodle_payload[:16].hex()}")
    # Decompress
    decompressed = oodle_decompress(oodle_payload, uncomp_size)
    if decompressed:
        print(f"[decomp] OK! {len(decompressed)} bytes (expected {uncomp_size})")
        print(f"[decomp] first 64 bytes: {decompressed[:64].hex()}")
    else:
        print(f"[decomp] FAILED")
else:
    print(f"[block] comp_type={comp_type} not handled yet")

reader.close()
