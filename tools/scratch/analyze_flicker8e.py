import re, collections
LOG = r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-23-012225\log.txt"
KNOWN = {'480f28cf':'EYES','6192fe1c':'MOUTH','25ad8e56':'MOUTH.vb1','d265427c':'MOUTHV','2cfd04ad':'BROW','75e2c70c':'GATE','06e86a68':'IB','b655c335':'POS'}
raw = open(LOG,'rb').read()
text = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else raw.decode('utf-8',errors='replace')
lines = text.splitlines()
def frame(l):
    m = re.match(r'\s*(\d{6})', l); return int(m.group(1)) if m else None
cur={'vb0':None,'vb1':None,'ib':None}; draws=[]; pending=None
for i,l in enumerate(lines):
    m=re.search(r'IASetVertexBuffers\(StartSlot:(\d+)',l)
    if m: pending=int(m.group(1)); continue
    if pending is not None:
        m=re.match(r'\s*\d+:\s+resource=\S+\s+hash=([0-9a-f]+)',l)
        if m: cur['vb%d'%pending]=m.group(1); continue
        pending=None
    m=re.search(r'IASetIndexBuffer\(pIndexBuffer:\S+,.*?hash=([0-9a-f]+)',l)
    if m: cur['ib']=m.group(1); continue
    m=re.search(r'DrawIndexed\(IndexCount:(\d+)',l)
    if m: draws.append((frame(l),i+1,int(m.group(1)),cur['vb0'],cur['vb1'],cur['ib']))

# face-part-like ICs: 4554(EYES),4014(MOUTH),132(BROW)
face_like=[d for d in draws if d[2] in (4554,4014,132)]
print("face-part-like draws (IC in 4554/4014/132):")
for d in face_like:
    tag = KNOWN.get(d[3],'UNKNOWN')
    print(f"  F{d[0]} L{d[1]} IC={d[2]} vb0={d[3]}({tag}) vb1={d[4]} ib={d[5]}")

# per-frame hash usage summary for unknown hashes incl ICs
print("\nunknown vb0 -> IC multiset:")
u=collections.defaultdict(collections.Counter)
for f,ln,ic,v0,v1,ib in draws:
    if v0 and v0 not in KNOWN: u[v0][ic]+=1
for h,c in u.items(): print(f"  {h}: {dict(c)}")

# frames where f6acc9e6 drawn
fr=sorted({f for f,ln,ic,v0,v1,ib in draws if v0=='f6acc9e6'})
print("\nf6acc9e6 frames:", fr)
fr2=sorted({f for f,ln,ic,v0,v1,ib in draws if v0=='911ff708'})
print("911ff708 frames:", fr2)

# do unknown hashes ever appear before F38?
pre=sorted({f for f,ln,ic,v0,v1,ib in draws if f<38 and v0})
print("\nframes<38 vb0s seen:", pre[:5], "count:", len(pre))
# total distinct vb0 hashes overall
allh=collections.Counter(d[3] for d in draws)
print("\nall vb0 counts:", dict(allh))
