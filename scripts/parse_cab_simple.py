"""Parse bundle 0 of nilou_full_v2.bin as Unity serialized file (CAB).

Look for the Unity SerializedFile header:
  u32 m_FileSize
  u32 m_Version
  u32 m_DataOffset
  u8  m_Endianess
  u8[3] m_Reserved
  u32 m_Version >= 22: bytes following the header

Note: 02050112 uses Unity 2017.4.30f1 per first 32 bytes.

For any object table, we need:
- m_TypesCount (u32)
- For each type:
    u32 classID (LE)
    u16 is_stripped
    u16 m_ScriptTypeIndex (if version >= 21)
    u64 m_ScriptID (if version >= 21 and is_stripped)
    m_TypeTree (variable, if not stripped)

- m_BigIDEnabled (u8) before object table if version >= 22
- m_ObjectCount (u32 or u64)
- For each object:
    if big: u64 pathID
    else:   u32 pathID
    if big: i64 byteStart
    else:   i32 byteStart, i32 byteSize
    u32 typeID
"""
import struct
import os
import sys

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144

def parse_cab(data, label):
    """Parse data as Unity serialized file, return object table."""
    print(f"\n=== {label} ({len(data)} bytes) ===")
    print(f"  first 32 bytes: {data[:32].hex()}")

    if len(data) < 32:
        print(f"  too small")
        return None

    # Standard header
    try:
        version = struct.unpack_from('<I', data, 4)[0]
        data_offset = struct.unpack_from('<I', data, 8)[0]
        endian = data[12]
        is_big = bool(data[13])
        print(f"  version={version}, data_offset={data_offset}, endian={endian}, is_big={is_big}")

        # If version >= 22, byte 13 is m_Endianess
        # If version >= 22, there's also a "is big ids" flag at offset 16 typically
        # Try to find ObjectCount at offset 16 first
        for pos in [16, 17, 18, 20, 28, 32, 36, 40]:
            if pos + 4 > len(data):
                continue
            v = struct.unpack_from('<I', data, pos)[0]
            if 0 < v < 5000:
                print(f"  candidate pos={pos}, u32={v}")
                # Read pathID/byteStart/byteSize/typeID table at this position
                # Standard pattern: for each object: pathID, byteStart, byteSize, typeID
                # Check next 256 bytes for typeID patterns
                # Or for structure: 4B-u32-2B-u16-2B-u16-4B-u32 (type definition)
                # Try: read 16 bytes (4 classIDs each separated by 4 bytes)
                pass

        # Try the most common pattern: header at offset 0
        # 0:4  size
        # 4:8  version
        # 8:12 dataOffset
        # 12   endian
        # 13:16 reserved
        # 16   isBigList (if version >= 22)
        # 17:21 objectCount (u32) - if NOT big
        # 17:25 objectCount (u64) - if big
        is_big_ids = False
        if version >= 22:
            is_big_ids = data[16] != 0
            print(f"  is_big_ids={is_big_ids}")

        off = 17
        if is_big_ids:
            obj_count = struct.unpack_from('<Q', data, off)[0]
            off += 8
        else:
            obj_count = struct.unpack_from('<I', data, off)[0]
            off += 4
        print(f"  objectCount={obj_count} at offset {off}")

        if obj_count > 10000:
            print(f"  >>> objectCount too high, this is wrong offset")
            return None

        # Read object table
        objects = []
        for i in range(min(obj_count, 50)):
            if is_big_ids:
                if off + 24 > len(data):
                    break
                path_id = struct.unpack_from('<q', data, off)[0]
                off += 8
                byte_start = struct.unpack_from('<q', data, off)[0]
                off += 8
                byte_size = struct.unpack_from('<I', data, off)[0]
                off += 4
                type_id = struct.unpack_from('<I', data, off)[0]
                off += 4
            else:
                if off + 16 > len(data):
                    break
                path_id = struct.unpack_from('<I', data, off)[0]
                off += 4
                byte_start = struct.unpack_from('<I', data, off)[0]
                off += 4
                byte_size = struct.unpack_from('<I', data, off)[0]
                off += 4
                type_id = struct.unpack_from('<I', data, off)[0]
                off += 4
            objects.append((path_id, byte_start, byte_size, type_id))

        # Print first 20
        print(f"  First {len(objects)} objects:")
        for i, (pid, bs, bsz, tid) in enumerate(objects[:20]):
            print(f"    [{i:3d}] pathID={pid:>10}  byteStart={bs:>10}  byteSize={bsz:>10}  typeID={tid}  (0x{tid:08x})")

        # Group by typeID
        type_counts = {}
        for pid, bs, bsz, tid in objects:
            type_counts[tid] = type_counts.get(tid, 0) + 1
        print(f"  Type counts: {dict(sorted(type_counts.items()))}")

        return (obj_count, objects, off)
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

# Read bundle 0
with open(NILOU_BIN, 'rb') as f:
    bundle0 = f.read(BUNDLE_SIZE)

result = parse_cab(bundle0, "Bundle 0")

# Also try various offsets to find the right CAB structure
print("\n=== Searching for known CAB magic patterns ===")
# Look for known classID 43 (Mesh) or 1152437153 (MdbComponent) as u32 LE
mesh_pattern = struct.pack('<I', 43)
mdb_pattern = struct.pack('<I', 1152437153)
results = []
for off in range(0, len(bundle0) - 4, 4):
    chunk = bundle0[off:off+4]
    if chunk == mesh_pattern:
        results.append((off, "Mesh (43)"))
    elif chunk == mdb_pattern:
        results.append((off, "MdbComponent (1152437153)"))
print(f"Found {len(results)} potential classIDs in bundle 0:")
for off, name in results[:30]:
    print(f"  offset=0x{off:08x}  {name}")
