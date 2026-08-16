"""Step 2: Find Nilou in MDB data
- Search for 'Avatar_Girl_Sword_Nilou' near .state names
- Extract .asb paths for Nilou-related states
- Identify which .blk files contain those .asb files
"""
import re

PATH = r'D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin'
with open(PATH, 'rb') as f:
    data = f.read()

# Find all .state occurrences (the MDB entries end with .state)
markers = [
    b'Avatar_Girl_Sword_Nilou',
    b'Avatar_Girl_Sword_',  # broader - all sword girls
    b'.asb\x00',
]

for m in markers:
    positions = []
    pos = 0
    while True:
        p = data.find(m, pos)
        if p == -1:
            break
        positions.append(p)
        pos = p + 1
    print(f"{m!r}: {len(positions)} occurrences")

# Find Nilou near .state names
print("\n=== Nilou near .state suffix ===")
nilou_positions = []
pos = 0
while True:
    p = data.find(b'Avatar_Girl_Sword_Nilou', pos)
    if p == -1:
        break
    nilou_positions.append(p)
    pos = p + 1

# For each Nilou, show context with .state suffix if nearby
for p in nilou_positions[:30]:
    # Search forward for .state within 200 bytes
    end = data.find(b'.state', p, p + 200)
    if end > 0:
        # Extract the full state name
        state_name = data[p:end + 6]
        # Decode to readable
        try:
            s = state_name.decode('ascii', errors='ignore')
        except:
            s = str(state_name)
        print(f"  0x{p:08x}: {s}")
    else:
        # Try backward for the .asb path
        asb_start = data.rfind(b'.asb', max(0, p-100), p)
        if asb_start > 0:
            asb_full = data[asb_start-100:asb_start+5]
            try:
                s = asb_full.decode('ascii', errors='ignore')
            except:
                s = str(asb_full)
            print(f"  0x{p:08x}: [asb-near] ...{s}")
        else:
            # Show raw bytes
            try:
                s = data[p:p+80].decode('ascii', errors='ignore')
            except:
                s = str(data[p:p+80])
            print(f"  0x{p:08x}: [no-state] {s!r}")
