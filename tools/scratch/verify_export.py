"""Compare source Face.obj vs scaled Face.obj (exported)."""
import os

SRC = r"D:\Documents\Default Project\Nilou\anime_nilou_08476697\Mesh\Face.obj"
OUT = r"D:\Documents\Default Project\Nilou\mod_shrink_test\head\Face.obj"

def bbox(path):
    xs = ys = zs = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('v '):
                _, x, y, z = line.split()
                xs.append(float(x)); ys.append(float(y)); zs.append(float(z))
    if not xs:
        return None
    return {
        'n': len(xs),
        'x': (min(xs), max(xs)),
        'y': (min(ys), max(ys)),
        'z': (min(zs), max(zs)),
    }

s = bbox(SRC)
o = bbox(OUT)

def delta(b): return b[1] - b[0]

print('=== Face.obj compare ===')
print(f"src   vtx={s['n']:4d}  Y range: {delta(s['y']):.6f}  (min={s['y'][0]:.4f}, max={s['y'][1]:.4f})")
print(f"out   vtx={o['n']:4d}  Y range: {delta(o['y']):.6f}  (min={o['y'][0]:.4f}, max={o['y'][1]:.4f})")

ratio_y = delta(o['y']) / delta(s['y'])
print(f"\nY range ratio: {ratio_y:.4f} (target 0.65)")
if abs(ratio_y - 0.65) < 0.02:
    print("[OK] Y scaled to ~0.65 — head shrink is working")
else:
    print(f"[WARN] Y ratio {ratio_y:.4f} far from target 0.65")

# Mask obj check too (other HEAD member)
m_src = bbox(r"D:\Documents\Default Project\Nilou\anime_nilou_08476697\Mesh\Mask.obj")
m_out = bbox(r"D:\Documents\Default Project\Nilou\mod_shrink_test\head\Mask.obj")
if m_src and m_out:
    ratio = delta(m_out['y']) / delta(m_src['y'])
    print(f"Mask Y ratio: {ratio:.4f}")

# Body obj (NOT scaled — should stay ~1.0)
b_src = bbox(r"D:\Documents\Default Project\Nilou\anime_nilou_08476697\Mesh\Body.obj")
b_out = bbox(r"D:\Documents\Default Project\Nilou\mod_shrink_test\body\Body.obj")
if b_src and b_out:
    ratio = delta(b_out['y']) / delta(b_src['y'])
    print(f"Body Y ratio: {ratio:.4f} (expect ~1.0 since BODY slot=1.0 default)")
    if 0.99 <= ratio <= 1.01:
        print("[OK] Body untouched as expected")
