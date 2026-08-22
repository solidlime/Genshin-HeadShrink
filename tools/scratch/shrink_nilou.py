"""
shrink_nilou.py — head-shrink comparison render
1. Import all 25 .obj from Mitya bundle
2. Render BASELINE (no modification)
3. Identify head meshes (Face*, Face_Eye*, Brow*, Bang*, Pupil*, EyeStar) vs body
4. Scale head meshes by HEAD_SCALE around each mesh's bounding-box center
5. Render SHRUNK
6. Save both PNGs side-by-side

Usage: blender -b --python shrink_nilou.py [-- HEAD_SCALE]
"""
import bpy
import os
import sys
from mathutils import Vector

OBJ_DIR = r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh"
OUT_DIR = r"D:\Documents\Default Project\Nilou\render_test"

os.makedirs(OUT_DIR, exist_ok=True)

HEAD_SCALE = float(sys.argv[sys.argv.index('--') + 1]) if '--' in sys.argv and len(sys.argv) > sys.argv.index('--') + 1 else 0.65

# Patterns: head = face/eyes/brows/hair/pupils; everything else = body
HEAD_PREFIXES = ('Face', 'Brow', 'Bang', 'Pupil', 'EyeStar')
BODY_PREFIXES = ('Body', 'EffectMesh', 'Area_Zd_Build')

# Clear scene
bpy.ops.wm.read_factory_settings(use_empty=False)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# Import
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

print(f"[import] {len(imported)} objects")

# Classify
head_objs = []
body_objs = []
for o in imported:
    base = o.name.split('.')[0]
    if any(base.startswith(p) for p in HEAD_PREFIXES):
        head_objs.append(o)
    elif any(base.startswith(p) for p in BODY_PREFIXES):
        body_objs.append(o)
    else:
        body_objs.append(o)  # default

print(f"[classify] head={len(head_objs)}, body={len(body_objs)}")

# Combined bbox
verts = []
for o in imported:
    if o.type != 'MESH': continue
    for v in o.data.vertices:
        verts.append(o.matrix_world @ v.co)
bb_min = Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
bb_max = Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
center = (bb_min + bb_max) / 2
size = bb_max - bb_min

def setup_scene(name):
    """Setup camera + light + render path. Caller must place objects first."""
    # 3/4 front view: camera offset in +X and -Y (Unity's "front" is +Z, but our
    # scene's character is at origin and we view from -Z looking +Z).
    cam_dist = max(size.x, size.y, size.z) * 2.0
    cam_loc = Vector((cam_dist * 0.3, -cam_dist * 0.85, center.z + size.z * 0.4))
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.active_object
    bpy.context.scene.camera = cam
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    # Light: 3-point setup
    bpy.ops.object.light_add(type='SUN', location=(cam_dist * 0.4, -cam_dist * 0.4, cam_dist * 0.8))
    bpy.context.active_object.data.energy = 3.0
    bpy.context.scene.render.resolution_x = 900
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.filepath = os.path.join(OUT_DIR, name)

def render(name):
    setup_scene(name)
    bpy.ops.render.render(write_still=True)
    print(f"[render] {name}")

# --- BASELINE ---
render("nilou_baseline.png")

# --- APPLY SHRINK to head meshes ---
# Each head mesh: scale around its own bounding-box center (in object space, pre matrix)
for o in head_objs:
    if o.type != 'MESH':
        continue
    # Local bbox center
    local_verts = [v.co for v in o.data.vertices]
    if not local_verts:
        continue
    local_min = Vector((min(v.x for v in local_verts), min(v.y for v in local_verts), min(v.z for v in local_verts)))
    local_max = Vector((max(v.x for v in local_verts), max(v.y for v in local_verts), max(v.z for v in local_verts)))
    local_center = (local_min + local_max) / 2

    # Apply: translate center to origin, scale, translate back (in local space)
    mw = o.matrix_world.copy()
    o.matrix_world = mw  # ensure
    # Use bmesh for transform on vertices
    for v in o.data.vertices:
        v.co = local_center + (v.co - local_center) * HEAD_SCALE
    o.data.update()

print(f"[shrink] applied HEAD_SCALE={HEAD_SCALE} to {len(head_objs)} head meshes")

# --- SHRUNK ---
render("nilou_shrunk.png")

print(f"[done] scale={HEAD_SCALE}")
