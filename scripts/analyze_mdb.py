"""Analyze decompressed bundle structures - find MdbComponent signature."""
import sys
from pathlib import Path

MITYA = Path(r'D:\Documents\Default Project\Nilou\mitya_full_decompressed.bin')
NILOU = Path(r'D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin')

mitya = MITYA.read_bytes()
nilou = NILOU.read_bytes()

# Look at first bundle headers (each bundle starts with custom header)
print(f'Mitya size: {len(mitya):,}')
print(f'Nilou size: {len(nilou):,}')
print()

# Search for known Unity magic
for name, data in [('Mitya', mitya), ('Nilou', nilou)]:
    print(f'=== {name} ({len(data):,} bytes) ===')
    for magic in [b'UnityFS', b'UnityRaw', b'UnityWeb', b'TypeTree', b'Mesh', b'SkinnedMesh',
                  b'\x00\x00\x01\xc5', b'\x00\x00\x01\x00', b'MDB', b'mdb', b'Cab-',
                  b'\x8c\x06', b'\xcd\xab', b'm_Mesh', b'Avatar_Girl_Sword_Nilou',
                  b'Avatar_Boy_Catalyst_Mitya', b'MeshData', b'MeshDataBlock']:
        count = data.count(magic)
        if count > 0:
            print(f'  "{magic[:16].hex()}": {count} occurrences')

# Find positions of bundles (look for size-prefixed headers)
# Nilou first 256 bytes (first bundle header)
print(f'\n=== Nilou first 256 bytes ===')
print(nilou[:256].hex(' '))
print()
print(f'=== Mitya first 256 bytes ===')
print(mitya[:256].hex(' '))

# Find all "Blb\x03" markers in decompressed data (would be unexpected, but check)
print(f'\nBlb\x03 markers: Mitya={mitya.count(b"Blb\\x03")}, Nilou={nilou.count(b"Blb\\x03")}')