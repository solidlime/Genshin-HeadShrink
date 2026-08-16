"""analyze_gap3.py - ok/ng/最新 mod の縮小範囲比較 (首まで縮小されてたか)"""
import struct, sys, os

def read_buf(path, stride=40):
    with open(path, 'rb') as f:
        data = f.read()
    n = len(data) // stride
    return [struct.unpack_from('<3f', data, i*stride) for i in range(n)]

def bucket_moves(base, key, axis, nb=12):
    """axis 軸 (game 座標) でバケット化し、各バケットの平均移動量を返す"""
    moves = {}
    for i, (bp, kp) in enumerate(zip(base, key)):
        dm = sum((kp[j]-bp[j])**2 for j in range(3))**0.5
        bi = int((bp[axis] + 1.2) / 2.4 * nb)
        bi = max(0, min(nb-1, bi))
        moves.setdefault(bi, []).append(dm)
    out = []
    for bi in sorted(moves):
        v = moves[bi]
        lo = -1.2 + bi * 2.4 / nb
        hi = lo + 2.4 / nb
        out.append((round(lo,2), round(hi,2), len(v), round(sum(v)/len(v),5)))
    return out

def main():
    base_dir = r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\assets\test"
    new_dir = r"G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink\Noelle"
    targets = [
        ("ok Head", os.path.join(base_dir, "Noelle_ok", "NoelleHeadBase.buf"), os.path.join(base_dir, "Noelle_ok", "NoelleHeadKey.buf")),
        ("ng Body", os.path.join(base_dir, "Noelle_ng", "NoelleBodyBase.buf"), os.path.join(base_dir, "Noelle_ng", "NoelleBodyKey.buf")),
        ("new Body", os.path.join(new_dir, "NoelleBodyBase.buf"), os.path.join(new_dir, "NoelleBodyKey.buf")),
    ]
    for name, bp, kp in targets:
        if not (os.path.exists(bp) and os.path.exists(kp)):
            print(f"{name}: MISSING {bp} / {kp}")
            continue
        base, key = read_buf(bp), read_buf(kp)
        print(f"\n=== {name} ({len(base)} verts) — game x (上下) バケット別平均移動 ===")
        for row in bucket_moves(base, key, 0):
            print(f"  x[{row[0]:+.2f}..{row[1]:+.2f}] n={row[2]:5d} avg_move={row[3]}")

if __name__ == "__main__":
    main()
