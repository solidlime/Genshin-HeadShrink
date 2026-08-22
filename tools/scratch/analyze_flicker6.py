# フレーム毎の詳細: 最初トークン=フレーム番号を検証し、Map/Draw/HSイベントを集計
import re, io, collections

LOG = r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-23-012225\log.txt"

sec_re = re.compile(r"\[TextureOverride\\.*?Sucrose\.ini\\([A-Za-z_0-9]+)\]")
tok_re = re.compile(r"^(\d{6}) ")
map_re = re.compile(r"^(\d{6}) Map\(pResource:0x[0-9A-Fa-f]+.*?hash=([0-9a-f]{8})")
draw_re = re.compile(r"^(\d{6}) (?:DrawIndexed|Draw)\(")

FACE = {"480f28cf": "eyes", "6192fe1c": "mouth", "d265427c": "mouthV", "2cfd04ad": "brow"}
GATE = {"75e2c70c": "bodygate", "06e86a68": "ib", "b655c335": "pos"}

frames = collections.defaultdict(lambda: {"lines": 0, "draws": 0, "maps": collections.Counter(),
                                          "hs": [], "face_draws": 0})
with io.open(LOG, encoding="utf-8", errors="replace") as f:
    for line in f:
        tm = tok_re.match(line)
        if not tm:
            continue
        fr = int(tm.group(1))
        d = frames[fr]
        d["lines"] += 1
        if draw_re.match(line):
            d["draws"] += 1
        mm = map_re.match(line)
        if mm:
            h = mm.group(2)
            tag = FACE.get(h) or GATE.get(h)
            if tag:
                d["maps"][tag] += 1
        sm = sec_re.search(line)
        if sm:
            name = sm.group(1)
            if "$is = 1" in line:
                d["hs"].append(name + ".$is1")
            elif "if $is: true" in line:
                d["hs"].append(name + ".RUN")

nums = sorted(frames)
print("frame range:", nums[0], "-", nums[-1], "| frames:", len(nums))
lens = [frames[n]["lines"] for n in nums]
print("lines/frame min-max:", min(lens), max(lens))

# サマリ: HS発火フレーム / face buffer Map フレーム / gate buffer Map フレーム
def has(d, sub):
    return any(sub in x for x in d["hs"])

print("\nfr | lines draws | maps(face/gate)          | HS events")
for n in nums:
    d = frames[n]
    fm = sum(c for k, c in d["maps"].items() if k in ("eyes", "mouth", "mouthV", "brow"))
    gm = sum(c for k, c in d["maps"].items() if k in ("bodygate", "ib", "pos"))
    hs = ",".join(d["hs"]) if d["hs"] else "-"
    mp = ",".join(f"{k}x{c}" for k, c in sorted(d["maps"].items())) or "-"
    print(f"{n:3d} | {d['lines']:4d} {d['draws']:4d}  | {mp:<24} | {hs}")
