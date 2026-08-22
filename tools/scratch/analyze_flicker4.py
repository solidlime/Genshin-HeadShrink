# T015後の点滅ダンプ解析: FrameAnalysis-2026-08-23-012225 (Sucrose solo)
# [Present] をフレーム境界とみなし、各フレームで HeadShrink セクションがどう発火したかを集計。
import re, io, collections

LOG = r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-23-012225\log.txt"

sec_re = re.compile(r"\[TextureOverride\\.*?Sucrose\.ini\\([A-Za-z_0-9]+)\]")

frames = collections.defaultdict(lambda: collections.Counter())
cur = 0
with io.open(LOG, encoding="utf-8", errors="replace") as f:
    for line in f:
        if "[Present]" in line and "3DMigoto" in line:
            cur += 1
            continue
        sm = sec_re.search(line)
        if sm:
            name = sm.group(1)
            if "$is = 1" in line:
                frames[cur][name + ":$is1"] += 1
            elif "if $is: true" in line:
                frames[cur][name + ":run"] += 1
            elif "if $is: false" in line:
                frames[cur][name + ":skip"] += 1

face_keys = ["SucroseEyes", "SucroseMouth", "SucroseMouth_d265427c", "SucroseBrow"]
all_frames = sorted(frames)
print("total present-frames:", cur, "| frames with HS activity:", len(all_frames),
      "| range:", all_frames[0], "-", all_frames[-1])

def fired(fr, tag):
    return any(k.startswith(p + ":" + tag) for p in face_keys for k in frames[fr])

run_frames = [fr for fr in all_frames if fired(fr, "run")]
skip_frames = [fr for fr in all_frames if fired(fr, "skip")]
gate_frames = [fr for fr in all_frames if any(k == "SucroseIB:$is1" for k in frames[fr])]
pos_frames = [fr for fr in all_frames if any(k == "SucrosePosition:$is1" for k in frames[fr])]
bodygate_frames = [fr for fr in all_frames if any(k == "BodyGate:$is1" for k in frames[fr])]

print("face RUN frames:", len(run_frames), run_frames[:50])
print("face SKIP frames:", len(skip_frames), skip_frames[:50])
print("IB gate $is=1 frames:", len(gate_frames), gate_frames[:15], "...")
print("Position $is=1 frames:", len(pos_frames), pos_frames[:15])
print("BodyGate $is=1 frames:", len(bodygate_frames), bodygate_frames[:15])

for fr in all_frames[:25]:
    print(fr, dict(frames[fr]))

if len(run_frames) > 1:
    gaps = [(run_frames[i], run_frames[i+1], run_frames[i+1]-run_frames[i])
            for i in range(len(run_frames)-1) if run_frames[i+1]-run_frames[i] > 1]
    print("gaps>1 between face-run frames:", gaps[:30])
