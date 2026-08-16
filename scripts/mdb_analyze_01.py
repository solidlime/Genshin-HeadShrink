"""Step 1: MDB header structure analysis
- Open 02050112 decompressed data (237MB)
- Find all "MDB_Engine_Editor" occurrences
- Dump 256 bytes before each occurrence to find common header pattern
- Compare adjacent patterns to identify fixed-size blocks
"""
import re, os, hashlib

PATH = r'D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin'
print(f"File: {PATH}")
print(f"Size: {os.path.getsize(PATH):,} bytes")

with open(PATH, 'rb') as f:
    data = f.read()

print(f"Loaded: {len(data):,} bytes")

# Find all MDB_Engine_Editor occurrences
marker = b'MDB_Engine_Editor'
positions = []
pos = 0
while True:
    p = data.find(marker, pos)
    if p == -1:
        break
    positions.append(p)
    pos = p + 1

print(f"\nMDB_Engine_Editor occurrences: {len(positions)}")
print(f"First 5 positions: {positions[:5]}")
print(f"Last 5 positions: {positions[-5:]}")

# Dump 256 bytes before each occurrence (header zone)
print(f"\n=== HEADER ANALYSIS (256 bytes before MDB_Engine_Editor) ===")
for i, p in enumerate(positions[:5]):
    start = max(0, p - 256)
    chunk = data[start:p]
    print(f"\n--- Occurrence {i} at offset 0x{p:08x} ---")
    # Hex dump with offsets
    for j in range(0, len(chunk), 16):
        hex_bytes = ' '.join(f'{b:02x}' for b in chunk[j:j+16])
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk[j:j+16])
        print(f"  0x{start+j:08x}: {hex_bytes:<48s} {ascii_str}")
