"""
import_nilou.py — Blender 5.2.0 headless script
Imports all 25 .obj meshes extracted from 00_00514567.blk (Nilou = Mitya)
and renders a test frame to confirm the geometry assembles into a recognizable character.

Usage:
  blender -b --python import_nilou.py
"""
import bpy
import os
import sys
from mathutils import Vector

OBJ_DIR = r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh"
OUT_DIR = r"D:\Documents\Default Project\Nilou\render_test"

os.makedirs(OUT_DIR, exist_ok=True)

# Clear scene (keep default world/lighting)
bpy.ops.wm.read_factory_settings(use_empty=False)
# Remove default cube/camera/light
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# Import all .obj files
imported = []
for fname in sorted(os.listdir(OBJ_DIR)):
    if not fname.lower().endswith(".obj"):
        continue
    path = os.path.join(OBJ_DIR, fname)
    before = set(o.name for o in bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path)
    after = set(o.name for o in bpy.data.objects)
    new_objs = [bpy.data.objects[n] for n in (after - before)]
    imported.extend(new_objs)
    print(f"[import] {fname}: {len(new_objs)} object(s)")

print(f"[import] total objects: {len(imported)}")

if not imported:
    print("[fatal] no objects imported"); sys.exit(1)

# Compute combined bounding box
all_verts = []
for o in imported:
    if o.type != 'MESH':
        continue
    for v in o.data.vertices:
        all_verts.append(o.matrix_world @ v.co)

if not all_verts:
    print("[fatal] no mesh vertices"); sys.exit(1)

bb_min = Vector((min(v.x for v in all_verts), min(v.y for v in all_verts), min(v.z for v in all_verts)))
bb_max = Vector((max(v.x for v in all_verts), max(v.y for v in all_verts), max(v.z for v in all_verts)))
center = (bb_min + bb_max) / 2
size = bb_max - bb_min
print(f"[bounds] min={bb_min}, max={bb_max}")
print(f"[bounds] center={center}, size={size}")

# Add camera — place at -Y looking at center, offset for typical 3/4 view
cam_dist = max(size.x, size.y, size.z) * 2.5
bpy.ops.object.camera_add(location=(cam_dist * 0.4, -cam_dist, center.z + size.z * 0.15))
cam = bpy.context.active_object
bpy.context.scene.camera = cam

# Point camera at center
direction = center - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# Add sun light
bpy.ops.object.light_add(type='SUN', location=(5, -5, 10))
sun = bpy.context.active_object
sun.data.energy = 3.0

# Add ambient (world background)
world = bpy.context.scene.world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs[0].default_value = (0.05, 0.05, 0.08, 1.0)  # dark blue
    bg.inputs[1].default_value = 1.0

# Render
bpy.context.scene.render.resolution_x = 900
bpy.context.scene.render.resolution_y = 1200
bpy.context.scene.render.film_transparent = False
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.filepath = os.path.join(OUT_DIR, "nilou_first.png")

bpy.ops.render.render(write_still=True)
print(f"[render] saved to {bpy.context.scene.render.filepath}")
