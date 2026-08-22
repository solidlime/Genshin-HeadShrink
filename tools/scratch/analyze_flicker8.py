import re, collections
LOG = r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-23-012225\log.txt"
KNOWN = {'480f28cf':'EYES','6192fe1c':'MOUTH','25ad8e56':'MOUTH.vb1','d265427c':'MOUTHV','2cfd04ad':'BROW','75e2c70c':'GATE','06e86a68':'IB','b655c335':'POS'}
lines = open(LOG, encoding='utf-8', errors='replace').read().splitlines()
def frame(l):
    m = re.match(r'(\d{6})', l)
    return int(m.group(1)) if m else None

present_frames = set()
for i,l in enumerate(lines):
    if '[Present]' in l and '$is = 0' in l:
        present_frames.add(frame(l))
allf = sorted({frame(l) for l in lines if frame(l)})
missing = [f for f in allf if f not in present_frames]
print("Q4: frames total", len(allf), "with Present $is=0:", len(present_frames))
print("missing:", missing[:60])

cur = {'vb0':None,'vb1':None,'ib':None}
draws = []
for i,l in enumerate(lines):
    m = re.search(r'IASetVertexBuffers\s+Slot=(\d+).*?hash=([0-9a-f]+)', l)
    if m: cur['vb'+m.group(1)] = m.group(2)
    m = re.search(r'IASetIndexBuffer.*?hash=([0-9a-f]+)', l)
    if m: cur['ib'] = m.group(1)
    m = re.search(r'DrawIndexed.*?IndexCount=(\d+)', l)
    if m:
        draws.append((frame(l), i+1, int(m.group(1)), cur['vb0'], cur['vb1'], cur['ib']))

small = [(f,ln,ic,v0) for f,ln,ic,v0,v1,ib in draws if ic <= 6000]
print("\nQ3: small IndexCount(<=6000) draws:", len(small))
byhash = collections.Counter(v0 for _,_,_,v0 in small)
for h,c in byhash.most_common():
    print(f"  vb0={h} ({KNOWN.get(h,'?')}): {c} draws")

faceframes = collections.defaultdict(list)
for f,ln,ic,v0,v1,ib in draws:
    tags = []
    for h,name in (('vb0',v0),('vb1',v1)):
        if h and h in KNOWN: tags.append(f"{KNOWN[h]}@{h}")
    if ib and ib in KNOWN: tags.append(f"{KNOWN[ib]}@ib")
    if tags: faceframes[f].append((ln,ic,tags))
print("\nQ2: frames with any known-hash bind at draw:")
for f in sorted(faceframes): print(" ", f, faceframes[f][:4])

def prof(a,b):
    ds = [(f,ln,ic,v0) for f,ln,ic,v0,_,_ in draws if a<=f<=b]
    cnt = collections.Counter(ic for _,_,ic,_ in ds)
    print(f"frames {a}-{b}: {len(ds)} draws, top IndexCounts:", cnt.most_common(10))
prof(50,70); prof(85,120)

print("\nQ1: $is/Sucrose lines F36-F48:")
for i,l in enumerate(lines):
    f = frame(l)
    if f is not None and 36<=f<=48 and ('$is' in l or ('Sucrose' in l and ('Map' in l or 'copying' in l))):
        print(f"  L{i+1} {l.strip()[:150]}")
