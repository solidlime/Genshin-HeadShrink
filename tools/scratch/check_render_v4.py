import os
d = r'D:\Documents\Default Project\Nilou\render_test_v4'
print('exists:', os.path.exists(d))
if os.path.exists(d):
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if os.path.isfile(p):
            print(f"  {f}  {os.path.getsize(p):,} bytes")
