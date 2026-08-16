import struct, os

def read_buf(path, stride=40):
    with open(path, 'rb') as f:
        data = f.read()
    n = len(data) // stride
    return [struct.unpack_from('<3f', data, i * stride) for i in range(n)]

def diff_stats(base, key):
    moves = [tuple(k[i] - b[i] for i in range(3)) for b, k in zip(base, key)]
    mags = [sum(m[i] * m[i] for i in range(3)) ** 0.5 for m in moves]
    avg = tuple(sum(m[i] for m in moves) / len(moves) for i in range(3))
    resid = [sum((m[i] - avg[i]) ** 2 for i in range(3)) ** 0.5 for m in moves]
    nz = sum(1 for m in mags if m > 1e-6)
    return {'nz': nz, 'n': len(base), 'avg_move': tuple(round(a, 5) for a in avg),
            'max_resid': round(max(resid), 5), 'max_mag': round(max(mags), 5)}

d = 'assets/test'
for ver in ['ok', 'ng']:
    print('=== Noelle_%s ===' % ver)
    for unit in ['Eyes', 'Mouth', 'Brow']:
        base = read_buf('%s/Noelle_%s/Noelle%sBase.buf' % (d, ver, unit))
        key = read_buf('%s/Noelle_%s/Noelle%sKey.buf' % (d, ver, unit))
        s = diff_stats(base, key)
        print('%s: moved=%d/%d avg_move=%s max_resid=%.5f max_mag=%.5f'
              % (unit, s['nz'], s['n'], s['avg_move'], s['max_resid'], s['max_mag']))
    unit = 'Head' if ver == 'ok' else 'Body'
    base = read_buf('%s/Noelle_%s/Noelle%sBase.buf' % (d, ver, unit))
    key = read_buf('%s/Noelle_%s/Noelle%sKey.buf' % (d, ver, unit))
    s = diff_stats(base, key)
    print('%s: moved=%d/%d avg_move=%s max_resid=%.5f max_mag=%.5f'
          % (unit, s['nz'], s['n'], s['avg_move'], s['max_resid'], s['max_mag']))

# Base が ok/ng で一致するか (同じダンプか)
print('=== Base cross-check (ok vs ng) ===')
for unit in ['Eyes', 'Mouth', 'Brow']:
    b_ok = read_buf('%s/Noelle_ok/Noelle%sBase.buf' % (d, unit))
    b_ng = read_buf('%s/Noelle_ng/Noelle%sBase.buf' % (d, unit))
    same = all(abs(b_ok[i][j] - b_ng[i][j]) < 1e-5 for i in range(len(b_ok)) for j in range(3))
    print('%s Base same: %s' % (unit, same))
