import os, re, collections, glob
ROOTS=[r"G:\XXMI-Launcher-Portable\Mods", r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\assets\Dump"]
pat=re.compile(r'^(\d{6})-(vb[01]|ib)=([0-9a-f]{8})-.*\.buf$',re.I)
byhash=collections.defaultdict(list)
for root in ROOTS:
    for dp,_,fns in os.walk(root):
        for fn in fns:
            m=pat.match(fn)
            if m and m.group(2)=='vb0':
                byhash[m.group(3)].append(os.path.join(dp,fn))
def first(h): return sorted(byhash[h])[0]
def diff(a,b,n=4096):
    A=open(a,'rb').read(n); B=open(b,'rb').read(min(n,os.path.getsize(b)))
    L=min(len(A),len(B))
    return sum(x==y for x,y in zip(A[:L],B[:L]))/L if L else 0
known_sizes={'6192fe1c':35080,'d265427c':35080,'480f28cf':48960,'2cfd04ad':1920}
print("candidates within +-10% of known face vb0 sizes:")
seen=set()
for kh,ks in known_sizes.items():
    lo,hi=ks*0.9,ks*1.1
    for h,paths in byhash.items():
        if h in seen or h in known_sizes: continue
        sz=os.path.getsize(paths[0])
        if lo<=sz<=hi:
            seen.add(h)
            print(f"  {h} size={sz} (vs {kh} {ks}) n={len(paths)} first={first(h)}")
            print(f"    match4KB vs {kh}: {diff(first(kh),first(h)):.3f}")
print("\naa41c13a in vb0 scan:", 'aa41c13a' in byhash)
hits=glob.glob(r"G:\XXMI-Launcher-Portable\Mods\**\*aa41c13a*",recursive=True)+glob.glob(r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\assets\Dump\**\*aa41c13a*",recursive=True)
print("aa41c13a files:", len(hits))
for p in hits[:3]: print("  ",p, os.path.getsize(p))
