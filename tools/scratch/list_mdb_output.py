import os
d = r'D:\Documents\Default Project\Nilou'
print('=== MDB/scan related files ===')
for f in sorted(os.listdir(d)):
    p = os.path.join(d, f)
    if any(k in f.lower() for k in ('mdb', 'scan', 'log', 'mesh', 'asb', 'nilou')):
        if os.path.isfile(p):
            print(f'  {f:50s} {os.path.getsize(p):>12,}')
        elif os.path.isdir(p):
            print(f'  {f}/  (dir)')
