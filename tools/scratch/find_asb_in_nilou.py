"""Step 5: Search 02050112 decompressed data for Nilou's .asb hashes
- If found with surrounding bytes, the .asb is inside 02050112
- Search for Mesh classID (43 = 0x2B) or container hints near .asb
"""
import os

PATH = r'D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin'
with open(PATH, 'rb') as f:
    data = f.read()

# Nilou-referenced .asb hashes from MDB
ASB_HASHES = [
    b'b62b4e6b80a7d847',
    b'284f8f8a3a001b86',
    b'5e51e47d71876192',
    b'62a845a4c0b5f03a',
    b'21224b237a4d60cd',
    b'866084b651f90a4f',
]

# Also try broader pattern
print("=== Searching for .asb hashes in 02050112 decompressed data ===")
for h in ASB_HASHES:
    positions = []
    pos = 0
    while True:
        p = data.find(h, pos)
        if p == -1:
            break
        positions.append(p)
        pos = p + 1
    print(f"\n  {h.decode()}: {len(positions)} occurrences")
    for p in positions[:3]:
        # Show 32 bytes before, 16 after
        start = max(0, p - 32)
        end = min(len(data), p + 16)
        chunk = data[start:end]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        try:
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        except:
            ascii_str = ''
        print(f"    0x{p:08x}: {hex_str}")
        print(f"              {ascii_str}")

# Also try .asb pattern more broadly
print("\n=== All .asb paths with Nilou context ===")
# Find all .asb paths
asb_positions = []
pos = 0
while True:
    p = data.find(b'.asb\x00', pos)
    if p == -1:
        break
    asb_positions.append(p)
    pos = p + 1

print(f"Total .asb paths: {len(asb_positions)}")

# Try to find Nilou mesh-related .asb paths
# Look for paths within 30 bytes of a byte sequence that looks like Mesh header
# Unity Mesh classID in decompressed data: 0x2B 0x00 0x00 0x00 (LE 4 bytes)
# Or potentially a Mesh blob starting with m_Name string
# Easier: look for .asb paths in regions where we know meshes live

# Decompressed bundle starts: 02050112's first bundle has 2 nodes
# Let me find all "m_Name" style strings (Unity asset names)
# Or directly look for Mesh header bytes

# ClassID 43 (Mesh) in LE = 0x2B 00 00 00
# Search for this pattern in proximity to .asb paths
print("\n=== Mesh classID 43 (0x2B) occurrences ===")
mesh_class_positions = []
pos = 0
while True:
    p = data.find(b'\x2b\x00\x00\x00', pos)
    if p == -1:
        break
    mesh_class_positions.append(p)
    pos = p + 1
print(f"Total 0x2B 0x00 0x00 0x00 occurrences: {len(mesh_class_positions)}")
# Show first 5
for p in mesh_class_positions[:5]:
    start = max(0, p - 16)
    end = min(len(data), p + 32)
    chunk = data[start:end]
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    print(f"  0x{p:08x}: {hex_str}")
