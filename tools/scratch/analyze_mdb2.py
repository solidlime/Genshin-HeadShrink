"""Find structure around MDB markers and Nilou avatar name."""
from pathlib import Path

nilou = Path(r'D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin').read_bytes()
mitya = Path(r'D:\Documents\Default Project\Nilou\mitya_full_decompressed.bin').read_bytes()

# Find all MDB markers
mdb_positions = []
i = 0
while True:
    p = nilou.find(b'MDB', i)
    if p < 0:
        break
    mdb_positions.append(p)
    i = p + 1
print(f'MDB positions in Nilou: {len(mdb_positions)}')
print(f'First 10: {mdb_positions[:10]}')
print(f'First occurrence context (256B around):')
first = mdb_positions[0]
ctx = nilou[max(0,first-32):first+96]
print(f'  offset={first:#x}')
print(f'  ctx: {ctx.hex(" ")}')
print(f'  ascii: {ctx.decode("latin-1")}')

# Find Avatar_Girl_Sword_Nilou positions
nilou_positions = []
i = 0
while True:
    p = nilou.find(b'Avatar_Girl_Sword_Nilou', i)
    if p < 0:
        break
    nilou_positions.append(p)
    i = p + 1
print(f'\nAvatar_Girl_Sword_Nilou positions: {len(nilou_positions)}')
print(f'First 5: {nilou_positions[:5]}')

# Find Avatar_Boy_Catalyst_Mitya positions
mitya_positions = []
i = 0
while True:
    p = mitya.find(b'Avatar_Boy_Catalyst_Mitya', i)
    if p < 0:
        break
    mitya_positions.append(p)
    i = p + 1
print(f'\nAvatar_Boy_Catalyst_Mitya positions: {len(mitya_positions)}')
print(f'First 5: {mitya_positions[:5]}')

# For each Nilou avatar ref, show context
if nilou_positions:
    p = nilou_positions[0]
    print(f'\nFirst Avatar_Girl_Sword_Nilou at {p:#x}:')
    print(f'  before (64B): {nilou[max(0,p-64):p].hex(" ")}')
    print(f'  string:        {nilou[p:p+40].decode("latin-1", errors="replace")}')
    print(f'  after  (96B):  {nilou[p+40:p+136].hex(" ")}')

# For Mitya, show context
if mitya_positions:
    p = mitya_positions[0]
    print(f'\nFirst Avatar_Boy_Catalyst_Mitya at {p:#x}:')
    print(f'  before (64B): {mitya[max(0,p-64):p].hex(" ")}')
    print(f'  string:        {mitya[p:p+40].decode("latin-1", errors="replace")}')
    print(f'  after  (96B):  {mitya[p+40:p+136].hex(" ")}')

# Look at structure around first MDB in Nilou
print(f'\n=== First MDB region (offset 0-512 from MDB) ===')
print(nilou[first:first+512].hex(' '))

# Find all "Avatar_Girl" prefix (might catch variations)
for prefix in [b'Avatar_Girl_Sword_Nilou', b'Avatar_Girl_Sword_', b'Avatar_Girl_', b'Avatar_']:
    cnt = nilou.count(prefix)
    print(f'  prefix "{prefix.decode()}": {cnt}')