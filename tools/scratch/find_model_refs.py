"""Investigate structure around Avatar_Girl_Sword_Nilou strings in Nilou data."""
from pathlib import Path

NILOU = Path(r'D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin')
MITYA = Path(r'D:\Documents\Default Project\Nilou\mitya_full_decompressed.bin')

ndata = NILOU.read_bytes()
mdata = MITYA.read_bytes()
print(f'Nilou: {len(ndata):,} bytes')
print(f'Mitya: {len(mdata):,} bytes')

# Find all Avatar_Girl_Sword_Nilou references and dump surrounding context
pattern = b'Avatar_Girl_Sword_Nilou'
offsets = []
i = 0
while i < len(ndata) - len(pattern):
    j = ndata.find(pattern, i)
    if j < 0:
        break
    offsets.append(j)
    i = j + 1
print(f'\nAvatar_Girl_Sword_Nilou occurrences: {len(offsets)}')

# Show context around each
for idx, off in enumerate(offsets[:30]):
    # Show 64 bytes before, 80 after (capturing name + prefix)
    ctx_start = max(0, off - 64)
    ctx_end = min(len(ndata), off + 80)
    ctx = ndata[ctx_start:ctx_end]
    # Extract printable name (including prefix if present)
    end = ctx.find(b'\x00', off - ctx_start + len(pattern))
    if end < 0:
        end = ctx_end
    name_end = min(end, ctx_end)
    name = ndata[off:name_end]
    # Try to extract a longer name (preceded by non-null readable chars)
    name_start = off
    while name_start > 0 and ndata[name_start-1] not in (0, 0x0a, 0x0d, 0x09) and 32 < ndata[name_start-1] < 127:
        name_start -= 1
    full_name = ndata[name_start:end]
    print(f'  [{idx:2d}] off=0x{off:08x} name={full_name!r}')

# Look for Model_ variant
print('\n--- Looking for Model_ in Nilou ---')
pattern = b'Avatar_Girl_Sword_Nilou_Model'
offsets = []
i = 0
while True:
    j = ndata.find(pattern, i)
    if j < 0: break
    offsets.append(j)
    i = j + 1
print(f'Avatar_Girl_Sword_Nilou_Model occurrences: {len(offsets)}')
for off in offsets[:10]:
    end = ndata.find(b'\x00', off)
    if end < 0: end = off + 80
    full = ndata[off:end]
    print(f'  off=0x{off:08x} name={full!r}')

# Check Mitya for comparison
print('\n--- Mitya Avatar_Boy_Catalyst_Mitya occurrences ---')
pattern = b'Avatar_Boy_Catalyst_Mitya_Model'
offsets = []
i = 0
while True:
    j = mdata.find(pattern, i)
    if j < 0: break
    offsets.append(j)
    i = j + 1
print(f'Mitya Model occurrences: {len(offsets)}')
for off in offsets[:15]:
    end = mdata.find(b'\x00', off)
    if end < 0: end = off + 100
    full = mdata[off:end]
    print(f'  off=0x{off:08x} name={full!r}')