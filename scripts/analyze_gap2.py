import struct, math, os

def read_buf(path, stride=40):
    with open(path, 'rb') as f:
        data = f.read()
    n = len(data) // stride
    return [struct.unpack_from('<3f', data, i * stride) for i in range(n)]

def g2d(p):  # game -> display (表示座標)
    return (p[2], p[1], -p[0])

def mov(base, key):
    return [tuple(k[i] - b[i] for i in range(3)) for b, k in zip(base, key)]

LOC = {  # 境界マッチング収束値 (表示座標)
    'Eyes': (-0.0195, -0.0372, 0.3646),
    'Mouth': (-0.0215, -0.0507, 0.3673),
    'Brow': (-0.0238, -0.0233, 0.3750),
}

def compare(body_base_path, body_key_path, face):
    """face メッシュの境界ズレ (表示座標) を body と比較。"""
    body_base = read_buf(body_base_path)
    body_key = read_buf(body_key_path)
    body_mov = mov(body_base, body_key)
    body_disp = [g2d(b) for b in body_base]
    d = os.path.dirname(body_base_path)
    fb = read_buf(os.path.join(d, 'Noelle%sBase.buf' % face))
    fk = read_buf(os.path.join(d, 'Noelle%sKey.buf' % face))
    fm = mov(fb, fk)
    loc = LOC[face]
    gaps = []
    sampled = list(range(0, len(fb), 3))
    for i in sampled:
        g = g2d(fb[i])
        p = (g[0] + loc[0], g[1] + loc[1], g[2] + loc[2])
        best = None
        bd2 = 1e18
        for j in range(len(body_disp)):
            q = body_disp[j]
            d2 = (q[0]-p[0])**2 + (q[1]-p[1])**2 + (q[2]-p[2])**2
            if d2 < bd2:
                bd2 = d2
                best = j
        dist = math.sqrt(bd2)
        if dist > 0.02 or best is None:  # 境界頂点のみ
            continue
        g2 = tuple(fm[i][k] - body_mov[best][k] for k in range(3))
        gaps.append((dist, g2))
    gaps.sort(key=lambda t: t[0])
    n = max(1, len(gaps) // 2)
    close = gaps[:n]
    gm = tuple(sum(g[k] for _, g in close)/len(close) for k in range(3))
    gmag = [math.sqrt(sum(g[k]**2 for k in range(3))) for _, g in close]
    gy = [abs(g[1]) for _, g in close]
    print('%s: boundary_pairs=%d gap_mean=(%.5f,%.5f,%.5f) mag_median=%.5f y_median=%.5f y_max=%.5f'
          % (face, len(close), gm[0], gm[1], gm[2],
             sorted(gmag)[len(gmag)//2], sorted(gy)[len(gy)//2], max(gy)))

for label, base_dir, unit in [
        ('ok', 'assets/test/Noelle_ok', 'Head'),
        ('ng', 'assets/test/Noelle_ng', 'Body'),
        ('new', r'G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink\Noelle', 'Body')]:
    print('=== Noelle_%s ===' % label)
    for face in ['Eyes', 'Mouth', 'Brow']:
        compare(os.path.join(base_dir, 'Noelle%sBase.buf' % unit),
                os.path.join(base_dir, 'Noelle%sKey.buf' % unit), face)
