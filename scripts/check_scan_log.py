import os
p = r'D:\Documents\Default Project\Nilou\scan_mdb.log'
print('log exists:', os.path.exists(p))
if os.path.exists(p):
    print('log size:', os.path.getsize(p))
    with open(p) as f:
        content = f.read()
    print('--- log content ---')
    print(content)
print(f"\nmesh_bundles.txt exists: {os.path.exists(r'D:\Documents\Default Project\Nilou\mdb_mesh_bundles.txt')}")
