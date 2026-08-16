import os, re
d = r'D:\Documents\Default Project\Nilou\anime_nilou_v4\Mesh'
names = sorted([f for f in os.listdir(d) if f.endswith('.obj')])
# Character mesh candidates (single-word PascalCase, no underscore prefix)
char_names = [f for f in names if re.match(r'^[A-Z][a-zA-Z]*\.obj$', f)]
# Exclude scene/NPC/scenery
exclude = re.compile(r'(Property|DeathZone|AvatarObj|Area|Ani_|Build_|NPC|Eff_|Effect|Common|EffectMesh)', re.I)
char_clean = [f for f in char_names if not exclude.search(f)]
print(f"Total OBJs: {len(names)}")
print(f"Single-word PascalCase: {len(char_names)}")
print(f"After scenery exclude: {len(char_clean)}")
print("--- Character mesh candidates ---")
for f in char_clean:
    size = os.path.getsize(os.path.join(d, f))
    print(f"  {f:30s}  {size:>10,d} bytes")
