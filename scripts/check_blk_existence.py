"""Step 4: Check existence of .blk files for MDB-referenced .asb folder numbers
- MDB paths: 66131/b62b4e6b80a7d847.asb etc. — folder number may be .blk file id
- Check blocks/00/{N}.blk and persistent/blocks/00/{N}.blk
"""
import os

ROOTS = [
    r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks',
    r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\Persistent\AssetBundles\blocks',
]

FOLDER_NUMS = [66131, 66290, 66679, 66238, 710, 968]

for n in FOLDER_NUMS:
    zeros = str(n).zfill(8)
    print(f"\n=== {n} (zfill: {zeros}) ===")
    for root in ROOTS:
        for sub in ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12', '13', '14', '15']:
            p = os.path.join(root, sub, f"{zeros}.blk")
            if os.path.exists(p):
                size = os.path.getsize(p)
                print(f"  FOUND: {p} ({size:,} bytes)")
            # Also try without zfill
            p2 = os.path.join(root, sub, f"{n}.blk")
            if os.path.exists(p2):
                size = os.path.getsize(p2)
                print(f"  FOUND: {p2} ({size:,} bytes)")
