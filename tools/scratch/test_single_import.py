"""
test_single_import.py — minimal test of single OBJ import
"""
import bpy
import os

bpy.ops.wm.read_factory_settings(use_empty=False)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# Try importing one OBJ
test_file = r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh\Body.obj"
print(f"Importing: {test_file}")
print(f"File size: {os.path.getsize(test_file)}")

# Count lines first
with open(test_file) as f:
    lines = f.readlines()
v_count = sum(1 for l in lines if l.startswith("v "))
f_count = sum(1 for l in lines if l.startswith("f "))
print(f"File: v={v_count}, f={f_count}")

before = set(o.name for o in bpy.data.objects)
bpy.ops.wm.obj_import(filepath=test_file)
after = set(o.name for o in bpy.data.objects)
new_objs = [bpy.data.objects[n] for n in (after - before)]
print(f"Imported objects: {len(new_objs)}")
for o in new_objs:
    print(f"  {o.name}: type={o.type}, vertices={len(o.data.vertices) if o.type=='MESH' else 'n/a'}")
    if o.type == 'MESH' and len(o.data.vertices) > 0:
        bb = o.data.vertices[0].co
        print(f"    first vertex: {bb}")
        print(f"    mesh.matrix_world: {o.matrix_world}")
        print(f"    total verts: {len(o.data.vertices)}")
        print(f"    total polygons: {len(o.data.polygons)}")

# Try with explicit forward/up axis
print("\n=== Try with forward_axis='-Z', up_axis='Y' ===")
bpy.ops.wm.read_factory_settings(use_empty=False)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
before = set(o.name for o in bpy.data.objects)
try:
    bpy.ops.wm.obj_import(filepath=test_file, forward_axis='NEGATIVE_Z', up_axis='Y')
    after = set(o.name for o in bpy.data.objects)
    new_objs = [bpy.data.objects[n] for n in (after - before)]
    print(f"Imported: {len(new_objs)}")
    for o in new_objs:
        print(f"  {o.name}: type={o.type}, vertices={len(o.data.vertices) if o.type=='MESH' else 'n/a'}")
except Exception as e:
    print(f"Failed: {e}")

# Try legacy operator
print("\n=== Try import_scene.obj (legacy) ===")
bpy.ops.wm.read_factory_settings(use_empty=False)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
before = set(o.name for o in bpy.data.objects)
try:
    bpy.ops.import_scene.obj(filepath=test_file)
    after = set(o.name for o in bpy.data.objects)
    new_objs = [bpy.data.objects[n] for n in (after - before)]
    print(f"Imported: {len(new_objs)}")
    for o in new_objs:
        print(f"  {o.name}: type={o.type}, vertices={len(o.data.vertices) if o.type=='MESH' else 'n/a'}")
except Exception as e:
    print(f"Failed: {e}")
