import os
p = r'D:\Documents\Default Project\Nilou\mdb_mesh_bundles.txt'
print('exists:', os.path.exists(p))
if os.path.exists(p):
    print('size:', os.path.getsize(p))
    with open(p) as f:
        head = f.read(2000)
    print('--- first 2000 chars ---')
    print(head)
