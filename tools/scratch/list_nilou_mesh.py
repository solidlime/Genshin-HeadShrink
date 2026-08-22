import glob, os
files = sorted(glob.glob(r'D:\Documents\Default Project\Nilou\anime_nilou_v4\Mesh\*.obj'))
print(f'Total: {len(files)}')
# Filter character-style names
for f in files:
    name = os.path.basename(f)
    size = os.path.getsize(f)
    if any(k in name for k in ('Body', 'Face', 'Brow', 'Bang', 'Pupil', 'EyeStar', 'EffectMesh')):
        print(f'  {name}: {size} B')
