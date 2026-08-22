"""Parse bundle 0 — try both LE and BE Unity CAB."""
import struct
import os

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144

with open(NILOU_BIN, 'rb') as f:
    bundle0 = f.read(BUNDLE_SIZE)

# First 32 bytes BE-interpreted:
# 00 00 00 7d  = 125 (header string length)
# 00 00 f1 0c  = 61708 (matches compressed block size!)
# 00 00 00 11  = 17 (Unity version)
# 00 00 10 00  = 4096 (m_DataOffset)
# 00 00 00 00  = 0 (m_Endianess + reserved)
# 32 30 31 37  = "2017" (Unity version starts)

print("=== BE interpretation ===")
header_len = struct.unpack('>I', bundle0[0:4])[0]
print(f"header string length: {header_len}")
header_str = bundle0[4:4+header_len].decode('utf-8', errors='replace')
print(f"header string: {header_str[:200]}")

off = 4 + header_len
# After header: m_FileSize, m_Version, m_DataOffset, m_Endianess, m_Reserved
m_FileSize = struct.unpack('>I', bundle0[off:off+4])[0]
off += 4
m_Version = struct.unpack('>I', bundle0[off:off+4])[0]
off += 4
m_DataOffset = struct.unpack('>I', bundle0[off:off+4])[0]
off += 4
m_Endianess = bundle0[off]
off += 1
m_Reserved = bundle0[off:off+3]
off += 3
print(f"m_FileSize={m_FileSize}, m_Version={m_Version}, m_DataOffset={m_DataOffset}, endian={m_Endianess}, reserved={m_Reserved.hex()}")
print(f"offset after header: {off}")

# m_Version 17 = Unity 2017.x — supports typeID and typeTree
# m_Endianess = 0 means little endian for body data
# Read object table (LE since endian=0 means body is LE; but for Genshin this might be BE)

# Try LE body
print("\n=== LE body interpretation ===")
m_ObjectCount = struct.unpack('<I', bundle0[off:off+4])[0]
off += 4
print(f"m_ObjectCount={m_ObjectCount} at offset {off}")
if m_ObjectCount > 10000:
    print(f"  >>> too high, trying BE")
    # Reset offset
    off = 4 + header_len + 4 + 4 + 4 + 1 + 3
    m_ObjectCount = struct.unpack('>I', bundle0[off:off+4])[0]
    off += 4
    print(f"  BE m_ObjectCount={m_ObjectCount} at offset {off}")

# Try to read object table
print(f"\nReading {m_ObjectCount} objects from offset {off}")
objects = []
for i in range(min(m_ObjectCount, 30)):
    if off + 16 > len(bundle0):
        print(f"  out of data at offset {off}")
        break
    # LE: pathID(4), byteStart(4), byteSize(4), typeID(4)
    path_id = struct.unpack('<I', bundle0[off:off+4])[0]
    byte_start = struct.unpack('<I', bundle0[off+4:off+8])[0]
    byte_size = struct.unpack('<I', bundle0[off+8:off+12])[0]
    type_id = struct.unpack('<I', bundle0[off+12:off+16])[0]
    off += 16
    objects.append((path_id, byte_start, byte_size, type_id))

print(f"\nFirst {len(objects)} objects (LE):")
for i, (pid, bs, bsz, tid) in enumerate(objects):
    print(f"  [{i:3d}] pathID={pid:>10}  byteStart={bs:>10}  byteSize={bsz:>10}  typeID={tid}  (0x{tid:08x})")

# Count types
type_counts = {}
for pid, bs, bsz, tid in objects:
    type_counts[tid] = type_counts.get(tid, 0) + 1
print(f"\nType counts: {dict(sorted(type_counts.items()))}")

# Also try BE
print("\n=== BE body interpretation ===")
off_be = 4 + header_len + 4 + 4 + 4 + 1 + 3
m_ObjectCount_be = struct.unpack('>I', bundle0[off_be:off_be+4])[0]
off_be += 4
print(f"m_ObjectCount={m_ObjectCount_be} at offset {off_be}")
objects_be = []
for i in range(min(m_ObjectCount_be, 30)):
    if off_be + 16 > len(bundle0):
        break
    path_id = struct.unpack('>I', bundle0[off_be:off_be+4])[0]
    byte_start = struct.unpack('>I', bundle0[off_be+4:off_be+8])[0]
    byte_size = struct.unpack('>I', bundle0[off_be+8:off_be+12])[0]
    type_id = struct.unpack('>I', bundle0[off_be+12:off_be+16])[0]
    off_be += 16
    objects_be.append((path_id, byte_start, byte_size, type_id))

print(f"First {len(objects_be)} objects (BE):")
for i, (pid, bs, bsz, tid) in enumerate(objects_be):
    print(f"  [{i:3d}] pathID={pid:>10}  byteStart={bs:>10}  byteSize={bsz:>10}  typeID={tid}  (0x{tid:08x})")

type_counts_be = {}
for pid, bs, bsz, tid in objects_be:
    type_counts_be[tid] = type_counts_be.get(tid, 0) + 1
print(f"\nType counts: {dict(sorted(type_counts_be.items()))}")
