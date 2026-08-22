import hashlib
d = r'D:\Documents\Default Project\Nilou\render_test_v4'
for f in ['head_baseline.png', 'head_shrunk.png']:
    p = f"{d}\\{f}"
    with open(p, 'rb') as fh:
        data = fh.read()
    h = hashlib.md5(data).hexdigest()
    print(f"{f}: size={len(data):,} md5={h}")

# Check if all-Nilou meshes (no scenery) loaded
import os
mesh_dir = r'D:\Documents\Default Project\Nilou\anime_nilou_v4\Mesh'
all_obj = [f for f in os.listdir(mesh_dir) if f.endswith('.obj')]
EXCLUDE = ('Area_', 'Property_', 'DeathZone', 'AvatarObj_Ani_Quest', 'Build_', 'Common_', 'NPC_', 'Ani_')
char_obj = [f for f in all_obj if not any(f.startswith(p) for p in EXCLUDE)]
print(f"\nMesh dir total: {len(all_obj)}")
print(f"After exclude: {len(char_obj)}")
# Show first/last few
for f in sorted(char_obj)[:5]:
    print(f"  + {f}")
print("  ...")
for f in sorted(char_obj)[-5:]:
    print(f"  + {f}")
