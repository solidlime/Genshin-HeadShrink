import os
p = r'D:\Documents\Default Project\Nilou\test_scan.log'
print('exists:', os.path.exists(p))
if os.path.exists(p):
    print('size:', os.path.getsize(p))
    with open(p) as f:
        print(f.read())
