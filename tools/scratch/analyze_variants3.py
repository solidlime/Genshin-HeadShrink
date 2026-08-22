import os,glob,collections
def diff(a,b,n=4096):
    A=open(a,'rb').read(n);B=open(b,'rb').read(min(n,os.path.getsize(b)))
    L=min(len(A),len(B));return sum(x==y for x,y in zip(A[:L],B[:L]))/L if L else 0
suc=r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\assets\Dump\★ok\Sucrose\FrameAnalysis-2026-08-21-232554"
eyes=[p for p in glob.glob(suc+r"\*-vb0=480f28cf-*")]
cdb=[p for p in glob.glob(suc+r"\*-vb0=cdb4fd2a-*")]
print("Sucrose folder: 480f28cf n=",len(eyes)," cdb4fd2a n=",len(cdb))
if eyes and cdb:
    print("same-folder match:", round(diff(eyes[0],cdb[0]),3))
    # stride check via size
    print("sizes:", os.path.getsize(eyes[0]), os.path.getsize(cdb[0]))
# frames of each
import re
fr=lambda p:int(re.match(r'.*\\(\d{6})-',p).group(1))
print("480f28cf frames:", sorted(map(fr,eyes))[:20])
print("cdb4fd2a frames:", sorted(map(fr,cdb))[:20])
bar=r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\assets\Dump\★ok\Barbara\FrameAnalysis-2026-08-22-115941"
brow=[p for p in glob.glob(bar+r"\*-vb0=2cfd04ad-*")]
v9f=[p for p in glob.glob(bar+r"\*-vb0=9f0ab8cd-*")]
print("\nBarbara folder: 2cfd04ad n=",len(brow)," 9f0ab8cd n=",len(v9f))
if brow and v9f:
    print("same-folder match:", round(diff(brow[0],v9f[0]),3), "sizes:",os.path.getsize(brow[0]),os.path.getsize(v9f[0]))
    print("2cfd04ad frames:",sorted(map(fr,brow))[:10]," 9f0ab8cd frames:",sorted(map(fr,v9f))[:10])
