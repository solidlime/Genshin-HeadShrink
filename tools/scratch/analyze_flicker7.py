# IASetVertexBuffers/IndexBuffer のバインドハッシュをフレーム毎に抽出し、
# HSセクション発火フレーム vs 無発火フレームで何が違うかを見る
import re, io, collections

LOG = r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-23-012225\log.txt"

tok_re = re.compile(r"^(\d{6}) ")
iaset_re = re.compile(r"^\d{6} IASet(VertexBuffers|IndexBuffer)\(")
resline_re = re.compile(r"^\s+(\d+): resource=0x[0-9A-Fa-f]+ hash=([0-9a-f]{8})(.*)$")

KNOWN = {"480f28cf": "EYES", "6192fe1c": "MOUTH", "d265427c": "MOUTHV", "2cfd04ad": "BROW",
         "75e2c70c": "GATE", "06e86a68": "IB", "b655c335": "POS", "def7af36": "GATE_N"}

binds = collections.defaultdict(lambda: collections.Counter())
cur = 0
in_ia = False
with io.open(LOG, encoding="utf-8", errors="replace") as f:
    for line in f:
        tm = tok_re.match(line)
        if tm:
            cur = int(tm.group(1))
            in_ia = bool(iaset_re.match(line))
            continue
        if in_ia:
            rm = resline_re.match(line)
            if rm:
                slot, h, rest = rm.group(1), rm.group(2), rm.group(3)
                tag = KNOWN.get(h, h)
                extra = ""
                mstride = re.search(r"stride=(\d+)", rest)
                if mstride:
                    extra = f"/st{mstride.group(1)}"
                binds[cur][f"vb{slot}:{tag}{extra}"] += 1
        else:
            if iaset_re.match(line):
                in_ia = True

# 出力: 主要フレームのバインド一覧
for fr in [38, 39, 40, 41, 43, 46, 50, 55, 60, 65, 70, 73, 75, 78, 80, 85, 90, 100, 120, 140, 160]:
    if fr in binds:
        items = ", ".join(f"{k}x{c}" for k, c in sorted(binds[fr].items()))
        print(f"F{fr:3d}: {items}")
    else:
        print(f"F{fr:3d}: (no IASet)")

# フレーム毎に「キャラっぽい」バインド(既知ハッシュ or 大きなstride)の有無を集計
print("\nframes with known-hash binds:")
known_frames = collections.defaultdict(set)
for fr, cnt in binds.items():
    for k in cnt:
        tag = k.split(":")[1].split("/")[0]
        if tag in KNOWN.values():
            known_frames[fr].add(tag)
frames_sorted = sorted(known_frames)
print(" ".join(f"{fr}:{'+'.join(sorted(t))}" for fr, t in known_frames.items()))
