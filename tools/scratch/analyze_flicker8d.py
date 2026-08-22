import re, collections
LOG = r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-23-012225\log.txt"
KNOWN = {'480f28cf':'EYES','6192fe1c':'MOUTH','25ad8e56':'MOUTH.vb1','d265427c':'MOUTHV','2cfd04ad':'BROW','75e2c70c':'GATE','06e86a68':'IB','b655c335':'POS'}
raw = open(LOG, 'rb').read()
if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
    text = raw.decode('utf-16')
else:
    text = raw.decode('utf-8', errors='replace')
lines = text.splitlines()
def frame(l):
    m = re.match(r'\s*(\d{6})', l)
    return int(m.group(1)) if m else None

cur = {'vb0':None,'vb1':None,'ib':None}
draws = []
pending_slot = None
for i,l in enumerate(lines):
    f = frame(l)
    m = re.search(r'IASetVertexBuffers\(StartSlot:(\d+)', l)
    if m:
        pending_slot = int(m.group(1)); continue
    if pending_slot is not None:
        m = re.match(r'\s*\d+:\s+resource=\S+\s+hash=([0-9a-f]+)', l)
        if m:
            cur['vb%d'%pending_slot] = m.group(1); continue
        pending_slot = None
    m = re.search(r'IASetIndexBuffer\(pIndexBuffer:\S+,.*?hash=([0-9a-f]+)', l)
    if m:
        cur['ib'] = m.group(1); continue
    m = re.search(r'DrawIndexed\(IndexCount:(\d+)', l)
    if m:
        draws.append((f, i+1, int(m.group(1)), cur['vb0'], cur['vb1'], cur['ib']))
print("total draws:", len(draws), "with vb0:", sum(1 for d in draws if d[3]))

def prof(a,b,label):
    ds = [d for d in draws if a<=d[0]<=b]
    cnt = collections.Counter(ic for _,_,ic,_,_,_ in ds)
    print(f"{label}: {len(ds)} draws, top IC:", cnt.most_common(10))
prof(50,70,'F50-70'); prof(85,120,'F85-120')

small = [d for d in draws if d[2]<=6000]
print("\nQ3 small(<=6000):", len(small))
byhash = collections.Counter(d[3] for d in small)
for h,c in byhash.most_common(15): print(f"  vb0={h} ({KNOWN.get(h,'?')}): {c}")

faceframes = collections.defaultdict(list)
for d in draws:
    f,ln,ic,v0,v1,ib = d
    tags=[f"{KNOWN[h]}@{h}" for h in (v0,v1,ib) if h in KNOWN]
    if tags: faceframes[f].append((ln,ic,tags))
print("\nQ2 frames with known hashes bound at draw:")
for f in sorted(faceframes): print(" ", f, len(faceframes[f]), faceframes[f][:3])

unk = collections.Counter(d[3] for d in draws if d[0]>48 and d[3] and d[3] not in KNOWN)
print("\nunknown vb0 F49+:", unk.most_common(15))

m4014 = [d for d in draws if d[2]==4014]
print("\nIC=4014 draws:", [(d[0],d[1],d[3]) for d in m4014][:20])
