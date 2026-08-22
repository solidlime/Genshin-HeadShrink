"""Grep all .blk for 'Avatar_Girl_Sword_Nilou_Model' (raw, before decrypt)."""
import os, glob

roots = [
    r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks',
    r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks',
]

pattern = b'Avatar_Girl_Sword_Nilou_Model'
print(f'Searching for {pattern!r} in raw .blk files...')

hits = []
for root in roots:
    if not os.path.isdir(root):
        print(f'  skip: {root}')
        continue
    files = glob.glob(os.path.join(root, '**', '*.blk'), recursive=True)
    print(f'  {root}: {len(files)} files')
    for f in files:
        try:
            with open(f, 'rb') as fp:
                data = fp.read()
            if pattern in data:
                cnt = data.count(pattern)
                hits.append((cnt, f))
                print(f'    HIT: {cnt}x {f}')
        except OSError:
            pass

print(f'\nTotal hits: {len(hits)}')
hits.sort(reverse=True)
for cnt, f in hits[:10]:
    print(f'  {cnt}x {f}')