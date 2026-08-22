# タイムライン解析: op番号順にイベントを並べて burst/連続を判定する
import re, io

LOG = r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-23-012225\log.txt"

sec_re = re.compile(r"\[TextureOverride\\.*?Sucrose\.ini\\([A-Za-z_0-9]+)\]")
op_re = re.compile(r"^(\d+) ")
disp_re = re.compile(r"Dispatch\(ThreadGroupCountX:(\d+)")

events = []
with io.open(LOG, encoding="utf-8", errors="replace") as f:
    for line in f:
        m = op_re.match(line)
        if not m:
            continue
        op = int(m.group(1))
        sm = sec_re.search(line)
        if sm:
            name = sm.group(1)
            if "$is = 1" in line:
                events.append((op, name + ".$is1"))
            elif "if $is: true" in line:
                events.append((op, name + ".RUN"))
            elif "if $is: false" in line:
                events.append((op, name + ".skip"))
            continue
        dm = disp_re.search(line)
        if dm:
            n = int(dm.group(1))
            if n in (1224, 877, 48):
                events.append((op, f"DISPATCH({n})"))
                continue
            # 大きすぎるゲーム内dispatchは粗く表示
            if n > 100:
                events.append((op, f"gamedisp({n})"))

# 圧縮表示: 連続同一イベントは (n x count) にまとめる
out = []
prev = None
cnt = 0
for op, ev in events:
    if ev == prev:
        cnt += 1
    else:
        if prev is not None:
            out.append(f"{prev_op}:{prev}" + (f" x{cnt}" if cnt > 1 else ""))
        prev, cnt, prev_op = ev, 1, op
if prev is not None:
    out.append(f"{prev_op}:{prev}" + (f" x{cnt}" if cnt > 1 else ""))

print("total events:", len(events))
for chunk in out:
    print(chunk)

# DrawIndexed の総数とハッシュ別出現 (顔描画が何フレームあったかの手がかり)
import collections
draws = collections.Counter()
with io.open(LOG, encoding="utf-8", errors="replace") as f:
    for line in f:
        m = op_re.match(line)
        if m and ("DrawIndexed(" in line or "Draw(" in line):
            hm = re.search(r"hash=([0-9a-f]{8})", line)
            draws[hm.group(1) if hm else "?"] += 1
print("\ntop draw hashes:")
for h, c in draws.most_common(15):
    print(f"  {h}: {c}")
