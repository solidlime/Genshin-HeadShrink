"""
render_nilou_compare.py — head-focused before/after side-by-side render
- Zooms camera to head region for clear visibility of the shrink
- Outputs single composite PNG with baseline (left) | shrunk (right)
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
EXCLUDE_PREFIXES = ('Area_Zd_Build',)


def load_obj_manual(path):
    verts, faces = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if parts[0] == 'v':
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif parts[0] == 'f':
                indices = [int(p.split('/')[0]) - 1 for p in parts[1:]]
                if len(indices) == 3:
                    faces.append(tuple(indices))
                else:
                    for i in range(1, len(indices) - 1):
                        faces.append((indices[0], indices[i], indices[i+1]))
    return verts, faces


def create_mesh_object(name, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def compute_head_bbox(head_objs):
    """Combined bbox of head meshes only (in world coords)."""
    all_v = []
    for o in head_objs:
        if o.type != 'MESH':
            continue
        for v in o.data.vertices:
            all_v.append(o.matrix_world @ v.co)
    if not all_v:
        return None, None, None
    mn = Vector((min(v.x for v in all_v), min(v.y for v in all_v), min(v.z for v in all_v)))
    mx = Vector((max(v.x for v in all_v), max(v.y for v in all_v), max(v.z for v in all_v)))
    return mn, mx, (mn + mx) / 2


def setup_scene_camera(cam_target, cam_size, mode='full'):
    """Camera framing the given target/size.
    mode='full': 3/4 view of full character (slight 3D feel)
    mode='head': close-up on head with slight downward angle (portrait)
    mode='front': pure front-on view (straight-on portrait)
    """
    cam_dist = max(cam_size.x, cam_size.y, cam_size.z) * 3.5
    if mode == 'head':
        # Portrait view: camera at face height (slightly above center), looking horizontally at head
        # Image Y aligns with world Y so character stands upright
        cam_loc = Vector((cam_target.x - cam_dist * 0.15, cam_target.y + cam_dist * 0.15, cam_target.z + cam_dist))
    elif mode == 'front':
        cam_loc = Vector((cam_target.x, cam_target.y - 0.05, cam_target.z + cam_dist))
    else:  # full
        cam_loc = Vector((cam_target.x + cam_dist * 0.4, cam_target.y + cam_dist * 0.1, cam_target.z + cam_dist * 0.9))
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.active_object
    bpy.context.scene.camera = cam
    cam.rotation_euler = (cam_target - cam_loc).to_track_quat('-Z', 'Y').to_euler()
    # 3-point lighting for better visibility
    bpy.ops.object.light_add(type='SUN', location=(cam_dist * 0.5, cam_dist * 0.3, cam_dist))
    bpy.context.active_object.data.energy = 3.5
    bpy.ops.object.light_add(type='SUN', location=(-cam_dist * 0.5, cam_dist * 0.3, cam_dist * 0.3))
    bpy.context.active_object.data.energy = 1.5
    return cam


# === Build scene ===
bpy.ops.wm.read_factory_settings(use_empty=False)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

imported = []
for fname in sorted(os.listdir(OBJ_DIR)):
    if not fname.lower().endswith(".obj"):
        continue
    name = os.path.splitext(fname)[0]
    if any(name.startswith(p) for p in EXCLUDE_PREFIXES):
        continue
    verts, faces = load_obj_manual(os.path.join(OBJ_DIR, fname))
    if not verts or not faces:
        continue
    obj = create_mesh_object(name, verts, faces)
    imported.append(obj)

head_objs = [o for o in imported if any(o.name.split('.')[0].startswith(p) for p in HEAD_PREFIXES)]
body_objs = [o for o in imported if o not in head_objs]

# Head bbox (where head should be)
head_mn, head_mx, head_center = compute_head_bbox(head_objs)
print(f"[head_bbox] min={head_mn}, max={head_mx}, center={head_center}")
head_size = head_mx - head_mn

# === Render 1: BASELINE (head-focused) ===
# Use a generous frame so head + neck + body top are visible
cam_target = Vector((head_center.x, head_center.y - 0.15, head_center.z))
cam_size = Vector((head_size.x * 1.5, head_size.y * 2.2, head_size.z * 1.5))
bpy.ops.object.select_all(action='DESELECT')
setup_scene_camera(cam_target, cam_size, mode='head')

# Assign vertex colors / material for better visibility
for o in imported:
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.shade_smooth()
    o.select_set(False)
    mat = bpy.data.materials.new(o.name + "_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        # Tint head meshes pink, body meshes light gray
        if o in head_objs:
            bsdf.inputs[0].default_value = (0.95, 0.6, 0.75, 1.0)  # pink/skin
            bsdf.inputs[2].default_value = 0.1
        else:
            bsdf.inputs[0].default_value = (0.5, 0.5, 0.55, 1.0)  # gray
            bsdf.inputs[2].default_value = 0.05
    o.data.materials.append(mat)

bpy.context.scene.render.resolution_x = 700
bpy.context.scene.render.resolution_y = 900
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.filepath = os.path.join(OUT_DIR, "head_baseline.png")
bpy.ops.render.render(write_still=True)
print("[render] head_baseline.png")

# === Apply shrink ===
for o in head_objs:
    if o.type != 'MESH':
        continue
    local_v = [v.co.copy() for v in o.data.vertices]
    if not local_v:
        continue
    mn = Vector((min(v.x for v in local_v), min(v.y for v in local_v), min(v.z for v in local_v)))
    mx = Vector((max(v.x for v in local_v), max(v.y for v in local_v), max(v.z for v in local_v)))
    c = (mn + mx) / 2
    for v in o.data.vertices:
        v.co = c + (v.co - c) * HEAD_SCALE
    o.data.update()

# === Render 2: SHRUNK ===
# Remove old camera/light
for o in list(bpy.data.objects):
    if o.type in ('CAMERA', 'LIGHT'):
        bpy.data.objects.remove(o, do_unlink=True)
setup_scene_camera(cam_target, cam_size, mode='head')
bpy.context.scene.render.filepath = os.path.join(OUT_DIR, "head_shrunk.png")
bpy.ops.render.render(write_still=True)
print("[render] head_shrunk.png")

# === Compose side-by-side ===
try:
    from PIL import Image
    a = Image.open(os.path.join(OUT_DIR, "head_baseline.png"))
    b = Image.open(os.path.join(OUT_DIR, "head_shrunk.png"))
    w, h = a.size
    composite = Image.new('RGB', (w * 2 + 10, h), (32, 32, 32))
    composite.paste(a, (0, 0))
    composite.paste(b, (w + 10, 0))
    composite.save(os.path.join(OUT_DIR, "head_compare.png"))
    print("[composite] head_compare.png")
except Exception as e:
    print(f"[composite] failed: {e}")
