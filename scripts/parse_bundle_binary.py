"""Direct binary parser for Unity SerializedFile inside each 262144-byte bundle.

Structure (AnimeStudio SerializedFile.cs):
  compressed int m_Header.length
  string m_Header.content  (Unity version string)
  u32 m_FileSize
  u32 m_Version
  u32 m_DataOffset
  u8  m_Endianess
  u8[3] m_Reserved
  u8  m_IsBigIDFlag (if version >= 22)
  u32 m_ObjectCount (or u64 if big)
  For each object:
    if big:  u64 pathID, u64 byteStart, u32 byteSize, u32 typeID
    else:    u32 pathID, u32 byteStart, u32 byteSize, u32 typeID
  u32 m_TypeCount
  For each type:
    u32 classID
    u16 isStripped
    u16 m_ScriptTypeIndex
    ...

For our purposes:
- Just parse header + object table
- List typeIDs found
- Find all MdbComponent (1152437153) instances
- Dump raw bytes of those objects
"""
import struct
import os
import sys

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144
TOTAL_SIZE = 237167471
NUM_BUNDLES = TOTAL_SIZE // BUNDLE_SIZE

PATTERN = b"2017.4.30f1\n"

def read_compressed_int(data, off):
    """Read a 7-bit encoded int (Unity's format). Returns (value, new_offset)."""
    result = 0
    shift = 0
    while True:
        if off >= len(data):
            raise ValueError("EOF reading compressed int")
        b = data[off]
        result |= (b & 0x7F) << shift
        off += 1
        if (b & 0x80) == 0:
            break
        shift += 7
    return result, off

def parse_bundle(data, idx):
    """Parse a single bundle, return list of (typeID, pathID, byteStart, byteSize)."""
    if PATTERN not in data:
        return None

    # Find a position where CAB header might start (try offset 0)
    # Format: compressed int (length of header string) + string + filesize, version, data_offset, endian, reserved
    try:
        header_len, off = read_compressed_int(data, 0)
        if header_len > 4096 or header_len < 1:
            return None  # Suspicious
        if off + header_len > len(data):
            return None
        # Skip header string
        off += header_len

        # Read 4 u32 fields: filesize, version, data_offset, ...
        m_FileSize = struct.unpack_from('<I', data, off)[0]
        off += 4
        m_Version = struct.unpack_from('<I', data, off)[0]
        off += 4
        m_DataOffset = struct.unpack_from('<I', data, off)[0]
        off += 4
        m_Endianess = data[off]
        off += 1
        m_Reserved = data[off:off+3]
        off += 3

        is_big = m_Version >= 22 and bool(data[off])
        if m_Version >= 22:
            off += 1  # skip isBigIDFlag

        if is_big:
            obj_count = struct.unpack_from('<Q', data, off)[0]
            off += 8
        else:
            obj_count = struct.unpack_from('<I', data, off)[0]
            off += 4

        if obj_count > 100000:
            return None  # Suspicious

        objects = []
        for i in range(obj_count):
            if is_big:
                if off + 24 > len(data):
                    break
                pathID = struct.unpack_from('<q', data, off)[0]
                off += 8
                byteStart = struct.unpack_from('<q', data, off)[0]
                off += 8
                byteSize = struct.unpack_from('<I', data, off)[0]
                off += 4
                typeID = struct.unpack_from('<I', data, off)[0]
                off += 4
            else:
                if off + 16 > len(data):
                    break
                pathID = struct.unpack_from('<I', data, off)[0]
                off += 4
                byteStart = struct.unpack_from('<I', data, off)[0]
                off += 4
                byteSize = struct.unpack_from('<I', data, off)[0]
                off += 4
                typeID = struct.unpack_from('<I', data, off)[0]
                off += 4
            objects.append((typeID, pathID, byteStart, byteSize))

        return objects
    except Exception as e:
        return None

# Verify with bundle 0 first
print("=== Test bundle 0 ===", flush=True)
with open(NILOU_BIN, 'rb') as f:
    chunk = f.read(BUNDLE_SIZE)
objects = parse_bundle(chunk, 0)
if objects:
    print(f"Bundle 0: {len(objects)} objects", flush=True)
    for typeID, pathID, byteStart, byteSize in objects[:10]:
        print(f"  typeID={typeID} (0x{typeID:08x}) pathID={pathID} byteStart={byteStart} byteSize={byteSize}", flush=True)
else:
    print(f"Bundle 0: parse failed", flush=True)

# Try a different starting offset
print("\n=== Try bundle 0 from offset 16 ===", flush=True)
# Maybe header string is at offset 16
def parse_bundle_at(data, start_off, idx):
    try:
        header_len, off = read_compressed_int(data, start_off)
        if header_len > 4096 or header_len < 1:
            return None
        if off + header_len > len(data):
            return None
        off += header_len
        m_FileSize = struct.unpack_from('<I', data, off)[0]
        off += 4
        m_Version = struct.unpack_from('<I', data, off)[0]
        off += 4
        m_DataOffset = struct.unpack_from('<I', data, off)[0]
        off += 4
        m_Endianess = data[off]
        off += 1
        off += 3
        is_big = m_Version >= 22 and bool(data[off])
        if m_Version >= 22:
            off += 1
        if is_big:
            obj_count = struct.unpack_from('<Q', data, off)[0]
            off += 8
        else:
            obj_count = struct.unpack_from('<I', data, off)[0]
            off += 4
        if obj_count > 100000:
            return None
        objects = []
        for i in range(obj_count):
            if is_big:
                if off + 24 > len(data):
                    break
                pathID = struct.unpack_from('<q', data, off)[0]
                off += 8
                byteStart = struct.unpack_from('<q', data, off)[0]
                off += 8
                byteSize = struct.unpack_from('<I', data, off)[0]
                off += 4
                typeID = struct.unpack_from('<I', data, off)[0]
                off += 4
            else:
                if off + 16 > len(data):
                    break
                pathID = struct.unpack_from('<I', data, off)[0]
                off += 4
                byteStart = struct.unpack_from('<I', data, off)[0]
                off += 4
                byteSize = struct.unpack_from('<I', data, off)[0]
                off += 4
                typeID = struct.unpack_from('<I', data, off)[0]
                off += 4
            objects.append((typeID, pathID, byteStart, byteSize))
        return (objects, m_FileSize, m_Version, m_DataOffset, obj_count)
    except Exception as e:
        return None

# Try multiple offsets
for start in [0, 4, 16, 17, 20, 24]:
    result = parse_bundle_at(chunk, start, 0)
    if result:
        objects, fs, ver, do, cnt = result
        print(f"  start={start}: OK! filesize={fs}, version={ver}, data_offset={do}, obj_count={cnt}", flush=True)
        for typeID, pathID, byteStart, byteSize in objects[:5]:
            print(f"    typeID={typeID} pathID={pathID} byteStart={byteStart} byteSize={byteSize}", flush=True)
    else:
        print(f"  start={start}: FAIL", flush=True)
