"""
diagnose_import.py — diagnose OBJ import coordinate system
"""
import bpy
import os
from mathutils import Vector

OBJ_DIR = r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh"
OUT_DIR = r"D:\Documents\Default Project\Nilou\render_test"
os.makedirs(OUT_DIR, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=False)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

imported = []
for fname in sorted(os.listdir(OBJ_DIR)):
    if not fname.lower().endswith(".obj"):
        continue
    path = os.path.join(OBJ_DIR, fname)
    before = set(o.name for o in bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path)
    after = set(o.name for o in bpy.data.objects)
    for n in (after - before):
        imported.append(bpy.data.objects[n])

# Diagnostic: report each object's world bbox
print("\n=== Per-object world bbox ===")
print(f"{'name':<40} {'x_min':>10} {'x_max':>10} {'y_min':>10} {'y_max':>10} {'z_min':>10} {'z_max':>10}")
all_mins = [1e9, 1e9, 1e9]
all_maxs = [-1e9, -1e9, -1e9]
for o in imported:
    if o.type != 'MESH':
        print(f"{o.name:<40} (not mesh, type={o.type})")
        continue
    bb = [Vector((-1e9, -1e9, -1e9)), Vector((1e9, 1e9, 1e9))]
    for v in o.data.vertices:
        w = o.matrix_world @ v.co
        for i in range(3):
            bb[0][i] = min(bb[0][i], w[i])
            bb[1][i] = max(bb[1][i], w[i])
    print(f"{o.name:<40} {bb[0].x:>10.3f} {bb[1].x:>10.3f} {bb[0].y:>10.3f} {bb[1].y:>10.3f} {bb[0].z:>10.3f} {bb[1].z:>10.3f}")
    for i in range(3):
        all_mins[i] = min(all_mins[i], bb[0][i])
        all_maxs[i] = max(all_maxs[i], bb[1][i])

print(f"\n=== Combined ===")
print(f"X: {all_mins[0]:.3f} to {all_maxs[0]:.3f} (size {all_maxs[0]-all_mins[0]:.3f})")
print(f"Y: {all_mins[1]:.3f} to {all_maxs[1]:.3f} (size {all_maxs[1]-all_mins[1]:.3f})")
print(f"Z: {all_mins[2]:.3f} to {all_maxs[2]:.3f} (size {all_maxs[2]-all_mins[2]:.3f})")
print(f"Center: ({(all_mins[0]+all_maxs[0])/2:.3f}, {(all_mins[1]+all_maxs[1])/2:.3f}, {(all_mins[2]+all_maxs[2])/2:.3f})")

# Now: render with a frame that contains everything, plus annotations
center = Vector(((all_mins[0]+all_maxs[0])/2, (all_mins[1]+all_maxs[1])/2, (all_mins[2]+all_maxs[2])/2))
size = Vector((all_maxs[0]-all_mins[0], all_maxs[1]-all_mins[1], all_maxs[2]-all_mins[2]))

# Camera at fixed position: looking from +X+Y+Z 3/4 view at full character
cam_dist = max(size.x, size.y, size.z) * 2.5
cam_loc = Vector((cam_dist, -cam_dist, center.z + size.z * 0.5))
bpy.ops.object.camera_add(location=cam_loc)
cam = bpy.context.active_object
bpy.context.scene.camera = cam
cam.rotation_euler = (center - cam_loc).to_track_quat('-Z', 'Y').to_euler()

# Add axes indicator at origin (a small RGB cross)
bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=20, location=(0,0,0))
cyl = bpy.context.active_object
cyl.name = "X_AXIS_RED"
mat = bpy.data.materials.new("X_RED"); mat.diffuse_color = (1,0,0,1)
cyl.data.materials.append(mat)
cyl.rotation_euler = (0, 0, 1.5708)  # rotate to X axis

bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=20, location=(0,0,0))
cyl = bpy.context.active_object
cyl.name = "Y_AXIS_GREEN"
mat = bpy.data.materials.new("Y_GREEN"); mat.diffuse_color = (0,1,0,1)
cyl.data.materials.append(mat)
# Y axis already vertical

bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=20, location=(0,0,0))
cyl = bpy.context.active_object
cyl.name = "Z_AXIS_BLUE"
mat = bpy.data.materials.new("Z_BLUE"); mat.diffuse_color = (0,0,1,1)
cyl.data.materials.append(mat)
cyl.rotation_euler = (1.5708, 0, 0)  # rotate to Z axis

# Sun light
bpy.ops.object.light_add(type='SUN', location=(cam_dist, -cam_dist, cam_dist))
bpy.context.active_object.data.energy = 2.0

bpy.context.scene.render.resolution_x = 900
bpy.context.scene.render.resolution_y = 1200
bpy.context.scene.render.filepath = os.path.join(OUT_DIR, "diagnose.png")
bpy.ops.render.render(write_still=True)
print(f"\n[render] saved diagnose.png with axes indicator")
