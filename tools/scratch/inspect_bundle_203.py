"""Inspect bundle 203 (first MdbComponent bundlest) structure.

Look at:
- Hex dump of first 256 bytes
- Position of MdbComponent magic (0xA1CBB044)
- Position of Mesh magic (0x2B000000)
- Strings (find "Avatar_Girl", "Nilou", "Body", "Face" etc.)
"""
import os

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144

with open(NILOU_BIN, 'rb') as f:
    # Bundle 203
    f.seek(203 * BUNDLE_SIZE)
    data = f.read(BUNDLE_SIZE)

print(f"Bundle 203: {len(data)} bytes")

# Hex dump region 0-256
print("\n=== First 256 bytes ===")
for off in range(0, 256, 16):
    line = data[off:off+16]
    hex_str = ' '.join(f'{b:02x}' for b in line)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
    print(f"  0x{off:04x}  {hex_str:48s}  {ascii_str}")

# Find MdbComponent magic positions
MDBC_MAGIC = b'\xa1\xcb\xb0\x44'
MESH_MAGIC = b'\x2b\x00\x00\x00'

print(f"\n=== MdbComponent magic (0xA1CBB044) positions ===")
pos = 0
while True:
    p = data.find(MDBC_MAGIC, pos)
    if p == -1:
        break
    # Show 32 bytes around the position
    start = max(0, p - 16)
    end = min(len(data), p + 20)
    chunk = data[start:end]
    marker = ' ' * (3 * (p - start)) + '^^^'
    print(f"  offset 0x{p:04x} ({p}): {chunk[:16].hex()} ...")
    print(f"  {' ' * (3 * (p - start))}                ^^^ MdbComponent")
    # Show context
    for i in range(0, len(chunk), 16):
        line = chunk[i:i+16]
        hex_str = ' '.join(f'{b:02x}' for b in line)
        print(f"    0x{start+i:04x}  {hex_str}")
    pos = p + 1

print(f"\n=== Mesh magic (0x2B000000) positions (first 5) ===")
pos = 0
count = 0
while count < 5:
    p = data.find(MESH_MAGIC, pos)
    if p == -1:
        break
    print(f"  offset 0x{p:04x} ({p})")
    start = max(0, p - 8)
    end = min(len(data), p + 20)
    for i in range(0, end-start, 16):
        line = data[start+i:start+i+16]
        hex_str = ' '.join(f'{b:02x}' for b in line)
        print(f"    0x{start+i:04x}  {hex_str}")
    pos = p + 1
    count += 1

# Find strings of interest
print("\n=== Interesting strings ===")
for needle in [b'Avatar_', b'Nilou', b'Body', b'Face', b'Mesh', b'Head', b'Bone', b'Skinned', b'girl', b'sword']:
    p = data.find(needle)
    if p >= 0:
        ctx_start = max(0, p - 8)
        ctx_end = min(len(data), p + 64)
        ctx = data[ctx_start:ctx_end]
        ascii_ctx = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        print(f"  '{needle.decode()}' at 0x{p:04x}: {ascii_ctx}")
