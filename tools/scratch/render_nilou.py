"""
render_nilou.py — manual OBJ parser → direct bpy mesh creation
Avoids bpy.ops.wm.obj_import issues by reading OBJ files in pure Python
and creating bpy meshes via from_pydata. Also applies head shrink.
"""
import bpy
import os
import sys
from mathutils import Vector

OBJ_DIR = r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh"
OUT_DIR = r"D:\Documents\Default Project\Nilou\render_test"
os.makedirs(OUT_DIR, exist_ok=True)

HEAD_SCALE = float(sys.argv[sys.argv.index('--') + 1]) if '--' in sys.argv and len(sys.argv) > sys.argv.index('--') + 1 else 0.65

HEAD_PREFIXES = ('Face', 'Brow', 'Bang', 'Pupil', 'EyeStar', 'EffectMesh')
EXCLUDE_PREFIXES = ('Area_Zd_Build',)  # Scenery bundled with character — not part of Nilou


def load_obj_manual(path):
    """Parse OBJ file, return (vertices, faces) lists."""
    verts = []
    faces = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            tag = parts[0]
            if tag == 'v':
                # v x y z
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif tag == 'f':
                # f v1[/vt1][/vn1] v2[/vt2][/vn2] v3[/vt3][/vn3] ...
                # Faces may have 3+ verts. Triangulate if needed.
                indices = []
                for p in parts[1:]:
                    vi = int(p.split('/')[0]) - 1
                    indices.append(vi)
                if len(indices) == 3:
                    faces.append(tuple(indices))
                else:
                    # fan triangulation
                    for i in range(1, len(indices) - 1):
                        faces.append((indices[0], indices[i], indices[i+1]))
    return verts, faces


def create_mesh_object(name, verts, faces):
    """Create a bpy mesh from vertex/face data."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


# Clear scene
bpy.ops.wm.read_factory_settings(use_empty=False)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# Load all OBJs
imported = []
for fname in sorted(os.listdir(OBJ_DIR)):
    if not fname.lower().endswith(".obj"):
        continue
    name = os.path.splitext(fname)[0]
    if any(name.startswith(p) for p in EXCLUDE_PREFIXES):
        print(f"[skip] {name}: excluded scenery")
        continue
    path = os.path.join(OBJ_DIR, fname)
    verts, faces = load_obj_manual(path)
    if not verts or not faces:
        print(f"[skip] {name}: no geometry")
        continue
    obj = create_mesh_object(name, verts, faces)
    imported.append(obj)
    print(f"[load] {name}: {len(verts)} verts, {len(faces)} faces")

print(f"[load] total: {len(imported)} objects")

# Combined bbox in world coords (matrix_world is identity)
all_verts_world = []
for o in imported:
    if o.type != 'MESH':
        continue
    for v in o.data.vertices:
        all_verts_world.append(o.matrix_world @ v.co)

bb_min = Vector((min(v.x for v in all_verts_world), min(v.y for v in all_verts_world), min(v.z for v in all_verts_world)))
bb_max = Vector((max(v.x for v in all_verts_world), max(v.y for v in all_verts_world), max(v.z for v in all_verts_world)))
center = (bb_min + bb_max) / 2
size = bb_max - bb_min
print(f"[bounds] min={bb_min}")
print(f"[bounds] max={bb_max}")
print(f"[bounds] center={center}")
print(f"[bounds] size={size}")

# Classify
head_objs = [o for o in imported if any(o.name.split('.')[0].startswith(p) for p in HEAD_PREFIXES)]
body_objs = [o for o in imported if o not in head_objs]
print(f"[classify] head={len(head_objs)}, body={len(body_objs)}")


def setup_scene(name):
    cam_dist = max(size.x, size.y, size.z) * 2.0
    cam_loc = Vector((cam_dist * 0.3, -cam_dist * 0.85, center.z + size.z * 0.4))
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.active_object
    bpy.context.scene.camera = cam
    cam.rotation_euler = (center - cam_loc).to_track_quat('-Z', 'Y').to_euler()
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

# --- SHRINK head meshes ---
shrunk_count = 0
for o in head_objs:
    if o.type != 'MESH':
        continue
    local_verts = [v.co.copy() for v in o.data.vertices]
    if not local_verts:
        continue
    local_min = Vector((min(v.x for v in local_verts), min(v.y for v in local_verts), min(v.z for v in local_verts)))
    local_max = Vector((max(v.x for v in local_verts), max(v.y for v in local_verts), max(v.z for v in local_verts)))
    local_center = (local_min + local_max) / 2
    for v in o.data.vertices:
        v.co = local_center + (v.co - local_center) * HEAD_SCALE
    o.data.update()
    shrunk_count += 1

print(f"[shrink] applied HEAD_SCALE={HEAD_SCALE} to {shrunk_count} head meshes")

# --- SHRUNK ---
render("nilou_shrunk.png")

print(f"[done] scale={HEAD_SCALE}")
