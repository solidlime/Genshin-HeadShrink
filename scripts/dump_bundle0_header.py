"""Hex dump first 256 bytes of bundle 0, find Unity serialized file start."""
import os

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144

with open(NILOU_BIN, 'rb') as f:
    data = f.read(BUNDLE_SIZE)

print(f"Bundle 0: {len(data)} bytes")
print()

# Hex dump region 0-256 with offsets
for off in range(0, 256, 16):
    line = data[off:off+16]
    hex_str = ' '.join(f'{b:02x}' for b in line)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
    print(f"  0x{off:04x}  {hex_str:48s}  {ascii_str}")

print()
# Find "2017.4.30f1\n" position
version_str = b'2017.4.30f1\n'
pos = data.find(version_str)
print(f"'2017.4.30f1\\n' found at offset: {pos}")

# Try parsing at offset pos-13 (assume header is just before version)
for start in [0, 4, 8, 12, 16, 20, 24, 32, 129, 133, 137, 141, 145]:
    print(f"\n--- start offset {start} ---")
    if start + 13 > len(data):
        continue
    chunk = data[start:start+32]
    print(f"  first 32 bytes: {chunk.hex()}")
    # If start, the version string might be at offset 6 in Unity CAB
    # Standard Unity CAB: [string_length] [string] [u32 fileSize] [u32 version] [u32 dataOffset] [u8 endian] [u8[3] reserved]
    # For 2017.4.30f1\n string of length 13: 0x0d = 13
    # Look for 0x0d followed by "2017.4.30f1\n"
    needle = b'\x0d2017.4.30f1\n'
    npos = data.find(needle)
    print(f"  \\x0d + '2017.4.30f1\\n' found at: {npos}")
    if npos >= 0:
        # Parse as Unity serialized file starting at npos
        # offset 0: 0x0d (string length)
        # offset 1-13: header string
        # offset 14: u32 fileSize
        # offset 18: u32 version
        # offset 22: u32 dataOffset
        import struct
        hstart = npos + 1 + 13  # after string
        if hstart + 16 <= len(data):
            fileSize = struct.unpack_from('<I', data, hstart)[0]
            version = struct.unpack_from('<I', data, hstart+4)[0]
            dataOffset = struct.unpack_from('<I', data, hstart+8)[0]
            endian = data[hstart+12]
            print(f"  fileSize={fileSize} version={version} dataOffset={dataOffset} endian={endian}")
            if 13 <= version <= 22 and fileSize < 1000000:
                print(f"  >>> VALID! This is the Unity serialized file start")
                # Read object count
                off2 = hstart + 13
                is_big = version >= 22 and bool(data[off2])
                if version >= 22:
                    off2 += 1
                obj_count = struct.unpack_from('<Q' if is_big else '<I', data, off2)[0]
                print(f"  obj_count={obj_count} (big={is_big}) at offset {off2}")
