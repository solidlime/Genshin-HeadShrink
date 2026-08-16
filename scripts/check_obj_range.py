"""Quick check: parse Body.obj and report true bbox + per-axis ranges"""
import os

path = r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh\Body.obj"
xs, ys, zs = [], [], []
with open(path) as f:
    for line in f:
        if line.startswith("v "):
            parts = line.split()
            xs.append(float(parts[1]))
            ys.append(float(parts[2]))
            zs.append(float(parts[3]))
print(f"Body.obj: {len(xs)} verts")
print(f"  X: min={min(xs):.4f}, max={max(xs):.4f}, span={max(xs)-min(xs):.4f}")
print(f"  Y: min={min(ys):.4f}, max={max(ys):.4f}, span={max(ys)-min(ys):.4f}")
print(f"  Z: min={min(zs):.4f}, max={max(zs):.4f}, span={max(zs)-min(zs):.4f}")

# Combined across all OBJs
print("\n=== Combined across all OBJs ===")
all_x, all_y, all_z = [], [], []
for fname in sorted(os.listdir(r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh")):
    if not fname.endswith(".obj"): continue
    p = os.path.join(r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh", fname)
    with open(p) as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                all_x.append(float(parts[1]))
                all_y.append(float(parts[2]))
                all_z.append(float(parts[3]))
print(f"Total {len(all_x)} verts")
print(f"  X: min={min(all_x):.4f}, max={max(all_x):.4f}, span={max(all_x)-min(all_x):.4f}")
print(f"  Y: min={min(all_y):.4f}, max={max(all_y):.4f}, span={max(all_y)-min(all_y):.4f}")
print(f"  Z: min={min(all_z):.4f}, max={max(all_z):.4f}, span={max(all_z)-min(all_z):.4f}")

# Show which meshes have what range (to understand if some are bigger)
print("\n=== Per-mesh ranges (suspicious ones) ===")
for fname in sorted(os.listdir(r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh")):
    if not fname.endswith(".obj"): continue
    p = os.path.join(r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh", fname)
    xs2, ys2, zs2 = [], [], []
    with open(p) as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                xs2.append(float(parts[1])); ys2.append(float(parts[2])); zs2.append(float(parts[3]))
    xspan = max(xs2)-min(xs2); yspan = max(ys2)-min(ys2); zspan = max(zs2)-min(zs2)
    if xspan > 1 or yspan > 1 or zspan > 1:
        print(f"{fname}: x={xspan:.2f} y={yspan:.2f} z={zspan:.2f}")
