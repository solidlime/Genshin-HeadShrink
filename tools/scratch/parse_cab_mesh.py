"""Step 6: Parse Unity CAB structure inside 02050112 decompressed data
- Unity AssetBundle CAB has: header, type table, object table, objects
- Find CAB headers (magic) and parse object tables
- Find ClassID 43 (Mesh) objects inside
- Skip MdbComponent wrappers (1152437153 = 0x44B0CBA1)
"""
import struct

PATH = r'D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin'
with open(PATH, 'rb') as f:
    data = f.read()

# Unity CAB magic + header structure
# For Unity 2017.4 (version "2017.4.30f1" detected):
# Header: headerSize(i32), fileSize(i32), version(i32), dataOffset(i32), endianess(u8), reserved[3]
# Then: flags(serializeType i32)
# Then: typeCount(i32), objectCount(i32)
# Then: types array (typeID: i32, isStripped: u8, scriptTypeIndex: i16, ...)
# Then: objects array (pathID: i32, byteStart: u32, byteSize: u32, typeID: i32)

# Let's look at the first 32 bytes of each bundle position
# 02050112 has 1441 bundles - let's find bundle boundaries

# First, search for CAB magic bytes "UnityFS" or just look at 02050112 header
# Actually Unity CAB doesn't have magic - it's just header + data

# Look at first 256 bytes of decompressed data
print("First 512 bytes of decompressed data:")
for i in range(0, 512, 16):
    chunk = data[i:i+16]
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f"  0x{i:08x}: {hex_str:<48s} {ascii_str}")

# Look at 0x000057204xx (where MDB data starts in earlier analysis)
# Actually let me first find the bundle boundaries by looking for size patterns
# The decompressed data was formed by concatenating decompressed blocks
# Each block was a Unity serialized file

# Find positions where i32 patterns suggest new file headers
# Look for type 9 (Oodle) markers - actually those are gone now (decompressed)
# Look for typical Unity header: headerSize=0x14 (20) or similar small value at start

# Try a different approach: find all positions where the byte pattern looks like a Unity file header
# Unity 2017.4 header: headerSize (i32) | fileSize (i32) | version (i32)
# version is typically 17-22 for modern Unity
# headerSize is typically 0x14 (20) for small files, larger for big ones

# Look for high density of "type 43" (Mesh) in valid Unity object headers
# Object header for Mesh (pathID i32 + byteStart u32 + byteSize u32 + typeID i32 = 16 bytes)
# A 16-byte window where typeID = 43 (0x2B 0x00 0x00 0x00) at offset 12

# Filter: must have reasonable pathID (>= 0) and byteStart that aligns with valid data
mesh_obj_positions = []
limit = len(data) - 16
for i in range(0, limit, 4):  # aligned to 4-byte
    type_id = struct.unpack_from('<i', data, i + 12)[0]
    if type_id == 43:
        path_id = struct.unpack_from('<i', data, i)[0]
        byte_start = struct.unpack_from('<I', data, i + 4)[0]
        byte_size = struct.unpack_from('<I', data, i + 8)[0]
        # Sanity: pathID should be positive, byte_start should be reasonable, byte_size > 0
        if 0 <= path_id < 100000 and 0 < byte_start < 10000000 and 100 < byte_size < 10000000:
            mesh_obj_positions.append((i, path_id, byte_start, byte_size))

print(f"\nValid Mesh objects (typeID=43, sane pathID/byteStart/byteSize): {len(mesh_obj_positions)}")
for i, (pos, path_id, byte_start, byte_size) in enumerate(mesh_obj_positions[:20]):
    print(f"  pos=0x{pos:08x} pathID={path_id} byteStart=0x{byte_start:x} byteSize={byte_size}")
