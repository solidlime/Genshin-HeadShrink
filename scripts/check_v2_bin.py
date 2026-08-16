import os
p = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
print('exists:', os.path.exists(p))
if os.path.exists(p):
    print('size:', os.path.getsize(p))

# List candidate files
for fname in ['nilou_full_v2.bin', 'nilou_full_decompressed.bin',
              'mitya_full_decompressed.bin', 'mitya_full_v2.bin']:
    for d in [r'D:\Documents\Default Project\Nilou',
              r'D:\Documents\Default Project\Nilou\render_test_v4']:
        full = os.path.join(d, fname)
        if os.path.exists(full):
            print(f'  {full}  {os.path.getsize(full):,}')
