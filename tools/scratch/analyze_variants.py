import re, os, json, collections, glob
ROOTS = [r"G:\XXMI-Launcher-Portable\Mods", r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\assets\Dump"]
KNOWN = {
 '6192fe1c':'MOUTH','d265427c':'MOUTHV','480f28cf':'EYES','2cfd04ad':'BROW',
 '63f702ce':'EYES(Noelle)','0bcb587f':'EYES.vb1(N)','3049e662':'MOUTH.vb1(N)','ddf54429':'BROW(N)','da7f6805':'BROW.vb1(N)',
 'efa4da64':'MOUTH(Furina/Lynette/Nilou)','5c536604':'MOUTH.vb1(F/L/N)','f4d23e3c':'MOUTH(Furina/Lanyan/Mizuki)',
 '9c75320a':'BROW(Lynette/Yanfei)','c9846fd5':'MOUTH(Bar/Kokomi/Yanfei)','7a73d3b5':'MOUTH.vb1(B/K/Y)'}
pat = re.compile(r'^(\d{6})-(vb[01]|ib)=([0-9a-f]{8})-.*\.buf$', re.I)
files=[]
for root in ROOTS:
    for dp,_,fns in os.walk(root):
        for fn in fns:
            m=pat.match(fn)
            if m: files.append((os.path.join(dp,fn), dp, fn, m.group(2), m.group(3), os.path.getsize(os.path.join(dp,fn))))
print("total buf files matched:", len(files))
# hash -> sizes -> count
tbl=collections.defaultdict(lambda: collections.defaultdict(lambda: [0,set()]))
for full,dp,fn,typ,h,sz in files:
    t=tbl[(typ,h)][sz]; t[0]+=1; t[1].add(dp)
print("\nAll hashes by type:")
for (typ,h),sizes in sorted(tbl.items()):
    for sz,(cnt,dps) in sorted(sizes.items()):
        print(f"  {typ} {h} ({KNOWN.get(h,'?')}): size={sz} n={cnt} folder={sorted(dps)[0]}")
json.dump({f"{t}|{h}|{s}":[c,list(d)[0]] for (t,h),ss in tbl.items() for s,(c,d) in ss.items()}, open(r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\tools\scratch\variant_scan_raw.json","w"))
