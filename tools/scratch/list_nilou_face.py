import os
d = r'D:\Documents\Default Project\Nilou\anime_nilou_v4\Mesh'
files = sorted(os.listdir(d))
# Show all face/head/body variants
keys = ['body', 'face', 'brow', 'bang', 'pupil', 'eye', 'star', 'effect', 'hair', 'dress', 'weapon']
for f in files:
    if any(k in f.lower() for k in keys) and f.endswith('.obj'):
        size = os.path.getsize(os.path.join(d, f))
        # Only short single-word or FaceXX style names
        base = f[:-4]
        if len(base) <= 20 and ('_' not in base or base in ['Body_LOD1','Body_LOD2','Body_LOD3','Face_LOD2','Face_LOD3','Brow_LOD2','Brow_LOD3','Face_Eye_LOD2','Face_Eye_LOD3']):
            print(f"  {f:40s}  {size:>10,d}")
print()
print("--- All Face variants ---")
for f in files:
    if 'face' in f.lower() and f.endswith('.obj'):
        print(f"  {f}")
