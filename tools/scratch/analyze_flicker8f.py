import re, collections
LOG = r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-23-012225\log.txt"
raw=open(LOG,'rb').read()
text=raw.decode('utf-16') if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else raw.decode('utf-8',errors='replace')
lines=text.splitlines()
def fr(l):
    m=re.match(r'\s*(\d{6})',l); return int(m.group(1)) if m else None
draw=collections.Counter(); dii=collections.Counter(); inst=collections.Counter()
for l in lines:
    f=fr(l)
    if re.search(r'\bDraw\(',l): draw[f]+=1
    if re.search(r'DrawIndexed\(',l): dii[f]+=1
    if re.search(r'DrawIndexedInstanced',l): inst[f]+=1
print("frames with Draw():", sorted(draw)[:20], "...")
print("F48-72 Draw counts:", {f:draw.get(f,0) for f in range(48,73)})
print("F48-72 DrawIndexed counts:", {f:dii.get(f,0) for f in range(48,73)})
# big vertex draws
big=[(fr(l), l.strip()[:90]) for l in lines if re.search(r'Draw\(VertexCount:(\d+)',l) and int(re.search(r'VertexCount:(\d+)',l).group(1))>5000]
print("big Draw() calls:", big[:10])
