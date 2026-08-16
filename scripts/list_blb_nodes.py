"""Step 8: Iterate 1441 Blb3File bundles in 02050112.blk, list all node names
- Each bundle has nodes (file/directory entries)
- Find Nilou-related nodes
- This is the actual file structure inside the .blk
"""
import sys
from pathlib import Path
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
import blb_parser

BLK = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk'

with open(BLK, 'rb') as f:
    data = f.read()

import re
positions = [m.start() for m in re.finditer(b'Blb\x03', data)]
print(f'Total bundles: {len(positions)}')

# For each bundle, parse and list nodes
bundle_data = []
for i, pos in enumerate(positions):
    try:
        f3 = blb_parser.Blb3File(data, pos)
        nodes = [(n['name'], n['offset'], n['size'], n['is_dir']) for n in f3.nodes]
        bundle_data.append((i, pos, nodes))
    except Exception as e:
        bundle_data.append((i, pos, []))

print(f'Parsed {len(bundle_data)} bundles')

# Find Nilou-related nodes
print('\n=== Nilou-related nodes ===')
nilou_nodes = []
for idx, pos, nodes in bundle_data:
    for name, offset, size, is_dir in nodes:
        if 'nilou' in name.lower():
            nilou_nodes.append((idx, pos, name, offset, size, is_dir))
            print(f'  Bundle {idx} @ 0x{pos:x}: {name} (size={size}, is_dir={is_dir})')

print(f'\nTotal Nilou nodes: {len(nilou_nodes)}')

# Show all unique .asb names referenced by MDB
asb_refs = set()
for idx, pos, nodes in bundle_data:
    for name, offset, size, is_dir in nodes:
        if name.endswith('.asb'):
            asb_refs.add(name)

print(f'\nUnique .asb node names: {len(asb_refs)}')
for name in sorted(asb_refs)[:30]:
    print(f'  {name}')
if len(asb_refs) > 30:
    print(f'  ... and {len(asb_refs) - 30} more')

# Find bundles that contain Nilou-mesh-related .asb files
print('\n=== Bundles with Nilou-related .asb names ===')
nilou_asb = []
for idx, pos, nodes in bundle_data:
    for name, offset, size, is_dir in nodes:
        if name.endswith('.asb') and 'nilou' in name.lower():
            nilou_asb.append((idx, pos, name, size))
            print(f'  Bundle {idx} @ 0x{pos:x}: {name} (size={size})')
print(f'Total: {len(nilou_asb)}')
