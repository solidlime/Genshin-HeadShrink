"""Scan 41 MdbComponent bundles for character names. Find Nilou's bundle."""
import os

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144

# From scan_for_mdbc.py
MDBC_BUNDLES = [
    203, 204, 206, 207, 208, 210, 211, 213, 218, 220, 223, 225, 228,
    344, 359, 361, 362, 375, 387, 389, 390, 391, 396, 401, 404, 405, 406, 409,
    490, 495
    # + a few more from the 41 total
]

# Load file
print("Loading 237MB file...", flush=True)
with open(NILOU_BIN, 'rb') as f:
    data = f.read()
print(f"Loaded {len(data):,} bytes", flush=True)

# 41 MdbComponent bundles - need complete list
# Re-read mdb_mdbc_bundles.txt
mdbc_bundles = []
mdc_path = r'D:\Documents\Default Project\Nilou\mdb_mdbc_bundles.txt'
if os.path.exists(mdc_path):
    with open(mdc_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 1:
                try:
                    mdbc_bundles.append(int(parts[0]))
                except:
                    pass
    print(f"Loaded {len(mdbc_bundles)} MdbComponent bundles from file")

print(f"\n=== Character names in MdbComponent bundles ===")
for bundle_idx in mdbc_bundles:
    offset = bundle_idx * BUNDLE_SIZE
    chunk = data[offset:offset + BUNDLE_SIZE]
    # Find Avatar_xxx strings
    pos = 0
    found = []
    while True:
        p = chunk.find(b'Avatar_', pos)
        if p == -1:
            break
        # Read until null, period, or non-printable
        end = p + 7
        while end < len(chunk) and 32 <= chunk[end] < 127 and chunk[end] != 0:
            end += 1
        if end - p > 10 and end - p < 200:
            name = chunk[p:end].decode('ascii', errors='replace')
            found.append(name)
        pos = p + 1
    # Dedupe
    found_unique = list(set(found))[:5]
    if found_unique:
        print(f"  bundle {bundle_idx:4d}: {found_unique}")
    else:
        # Maybe stripped strings, look for other patterns
        print(f"  bundle {bundle_idx:4d}: (no Avatar_ strings)")

# Specific check for Nilou
print(f"\n=== Direct Nilou search ===")
for bundle_idx in mdbc_bundles:
    offset = bundle_idx * BUNDLE_SIZE
    chunk = data[offset:offset + BUNDLE_SIZE]
    if b'Nilou' in chunk or b'Avatar_Girl_Sword_Nilou' in chunk:
        # Find positions
        for needle in [b'Nilou', b'Avatar_Girl_Sword_Nilou']:
            pos = 0
            while True:
                p = chunk.find(needle, pos)
                if p == -1:
                    break
                ctx = chunk[p:p+80]
                ascii_ctx = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
                print(f"  bundle {bundle_idx}: '{needle.decode()}' at 0x{p:04x}: {ascii_ctx}")
                pos = p + 1

# Also check what AssetBundle name each MdbComponent bundle has
print(f"\n=== AssetBundle names in MdbComponent bundles ===")
for bundle_idx in mdbc_bundles:
    offset = bundle_idx * BUNDLE_SIZE
    chunk = data[offset:offset + BUNDLE_SIZE]
    # Look for .asb pattern
    pos = 0
    found_asb = []
    while True:
        p = chunk.find(b'.asb', pos)
        if p == -1:
            break
        # Find the start of the path (look backwards for non-printable)
        start = p
        while start > 0 and 32 <= chunk[start-1] < 127 and chunk[start-1] != 0:
            start -= 1
        if p - start > 5 and p - start < 100:
            path = chunk[start:p+4].decode('ascii', errors='replace')
            found_asb.append(path)
        pos = p + 1
    found_asb = list(set(found_asb))[:3]
    if found_asb:
        print(f"  bundle {bundle_idx:4d}: {found_asb}")
