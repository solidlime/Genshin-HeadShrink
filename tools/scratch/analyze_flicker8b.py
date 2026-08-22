import re, collections
LOG = r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-23-012225\log.txt"
KNOWN = {'480f28cf':'EYES','6192fe1c':'MOUTH','25ad8e56':'MOUTH.vb1','d265427c':'MOUTHV','2cfd04ad':'BROW','75e2c70c':'GATE','06e86a68':'IB','b655c335':'POS'}
lines = open(LOG, encoding='utf-8', errors='replace').read().splitlines()
def frame(l):
    m = re.match(r'(\d{6})', l)
    return int(m.group(1)) if m else None

cur = {'vb0':None,'vb1':None,'ib':None}
draws = []
last_iaset = None
for i,l in enumerate(lines):
    f = frame(l)
    m = re.match(r'\d{6} \S*\s*IASetVertexBuffers\(StartSlot:(\d+)', l)
    if m:
        last_iaset = int(m.group(1)); continue
    # indented child line with hash right after IASetVertexBuffers
    if last_iaset is not None:
        m = re.search(r'resource=\S+ hash=([0-9a-f]+)', l)
        if m and re.match(r'\d{6} 3DMigoto\s+\d+:', l):
            cur['vb%d'%last_iaset] = m.group(1); continue
        elif not l.strip().startswith(tuple('0123456789')) or 'hash=' not in l:
            pass
    if re.search(r'IASetIndexBuffer', l):
        last_iaset = 'ib'
        m = re.search(r'hash=([0-9a-f]+)', l)
        if m: cur['ib'] = m.group(1); last_iaset=None
        continue
    m = re.search(r'DrawIndexed\(IndexCount:(\d+)', l)
    if m:
        draws.append((f, i+1, int(m.group(1)), cur['vb0'], cur['vb1'], cur['ib']))
print("total draws:", len(draws))

# Q2 profiles
def prof(a,b,label):
    ds = [d for d in draws if a<=d[0]<=b]
    cnt = collections.Counter(ic for _,_,ic,_,_,_ in ds)
    print(f"{label}: {len(ds)} draws, top IC:", cnt.most_common(12))
prof(50,70,'F50-70'); prof(85,120,'F85-120')

# Q3: small draws on non-override frames
small = [(f,ln,ic,v0,v1,ib) for f,ln,ic,v0,v1,ib in draws if ic<=6000]
print("\nQ3: small(<=6000) draws:", len(small))
byhash = collections.Counter((v0) for _,_,_,v0,_,_ in small)
for h,c in byhash.most_common(15): print(f"  vb0={h} ({KNOWN.get(h,'?')}): {c}")

# known-hash presence per frame at draw time
faceframes = collections.defaultdict(list)
for d in draws:
    f,ln,ic,v0,v1,ib = d
    tags=[f"{KNOWN[h]}@{h}" for h in (v0,v1,ib) if h in KNOWN]
    if tags: faceframes[f].append((ln,ic,tags))
print("\nQ2: frames with known hashes bound:")
for f in sorted(faceframes): print(" ", f, len(faceframes[f]), faceframes[f][:3])

# unknown vb0 hashes on frames >48
unk = collections.Counter(v0 for f,ln,ic,v0,v1,ib in draws if f>48 and v0 and v0 not in KNOWN)
print("\nunknown vb0 F49+:", unk.most_common(15))
