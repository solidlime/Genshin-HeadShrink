"""make_vb_only_mod.py — VB-only head shrink: scale vb, leave IB alone.

Game draws face with original IB (full triangles). Our scaled VB makes the verts smaller
in shader. No IB override, no VertexLimitRaise, no Game freeze from buffer mismatch.

# ponytail: 最小 head shrink mod。Position だけ差し替え、IB は game のまま。
"""
import json
import re
import struct
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUMP_BASE = ROOT / 'assets' / 'Dump'
PREVIEW = ROOT / 'assets' / 'Preview'
CHARS = ['Ayaka', 'Chiori', 'Ganyu', 'Keqing C1', 'Kokomi', 'Mizuki', 'Nilou', 'Noelle']
STRIDE = 40

DRAW_RE = re.compile(
    r"^(\d+) DrawIndexed\(IndexCount:(\d+),\s*StartIndexLocation:(\d+),\s*BaseVertexLocation:(\d+)\)"
)
SHARED = {'vb0': {'c82fb483'}, 'ib': {'bf1830b6'}}


def parse_log(log_path):
    lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
    frame_vb = defaultdict(set); frame_ib = defaultdict(set)
    for ln in lines:
        m = re.match(r"^(\d+) 3DMigoto Dumping Buffer .*-vb0=([0-9a-f]+)", ln)
        if m: frame_vb[int(m.group(1))].add(m.group(2)); continue
        m = re.match(r"^(\d+) 3DMigoto Dumping Buffer .*-ib=([0-9a-f]+)", ln)
        if m: frame_ib[int(m.group(1))].add(m.group(2))
    draws = []
    for ln in lines:
        m = DRAW_RE.match(ln)
        if not m: continue
        frame = int(m.group(1)); ic = int(m.group(2))
        start = int(m.group(3)); base = int(m.group(4))
        vb_list = sorted(frame_vb.get(frame, set()))
        ib_list = sorted(frame_ib.get(frame, set()))
        if not vb_list or not ib_list: continue
        draws.append({'frame': frame, 'ic': ic, 'start': start, 'base': base,
                      'vb0': vb_list[0], 'ib': ib_list[0]})
    return draws


def find_dump_file(dump_dir, prefix, hash_, frame):
    pat = f"{frame:06d}-{prefix}={hash_}-*.buf"
    for f in Path(dump_dir).glob(pat):
        return f
    return None


def build_char(char, scale=0.65):
    dump_dir = DUMP_BASE / char
    preview_dir = PREVIEW / char
    preview_dir.mkdir(parents=True, exist_ok=True)

    log = dump_dir / 'log.txt'
    if not log.exists():
        print(f"[{char}] no log.txt", file=sys.stderr); return False

    draws = parse_log(log)
    cands = [d for d in draws
             if d['vb0'] not in SHARED['vb0'] and d['ib'] not in SHARED['ib']
             and 5000 <= d['ic'] <= 8000]
    if not cands:
        cands = [d for d in draws
                 if d['vb0'] not in SHARED['vb0'] and d['ib'] not in SHARED['ib']
                 and 3000 <= d['ic'] <= 12000]
    if not cands:
        cands = [d for d in draws
                 if d['vb0'] not in SHARED['vb0'] and d['ib'] not in SHARED['ib']
                 and 2000 <= d['ic'] <= 15000]
    if not cands:
        print(f"[{char}] no face candidate", file=sys.stderr); return False
    pairs = {}
    for d in cands:
        k = (d['vb0'], d['ib'])
        if k not in pairs or d['ic'] > pairs[k]['ic']:
            pairs[k] = d
    face = sorted(pairs.values(), key=lambda d: d['ic'], reverse=True)[0]

    face_vb = find_dump_file(dump_dir, 'vb0', face['vb0'], face['frame'])
    if not face_vb:
        print(f"[{char}] face vb file missing", file=sys.stderr); return False

    vb_data = face_vb.read_bytes()
    verts = len(vb_data) // STRIDE
    pos = bytearray(vb_data)
    for i in range(verts):
        x, y, z = struct.unpack_from('<3f', pos, i * STRIDE)
        pos[i*STRIDE : i*STRIDE+12] = struct.pack('<3f', x * scale, y * scale, z * scale)
    scaled_vb = bytes(pos)

    # Write VB-only mod files
    (preview_dir / f'{char}Position.buf').write_bytes(scaled_vb)
    hash_json = json.dumps({'position': face['vb0']}, indent=2)
    (preview_dir / 'hash.json').write_text(hash_json)

    # Minimal .ini: only vb0 override, original IB untouched, no VertexLimitRaise
    ini = f"""\
; {char}
; HeadShrink — VB-only: scales vertex positions in face vb, leaves IB untouched.
; Game uses original IB → full face triangles drawn with shrunk positions.

[TextureOverride{char}Position]
hash = {face['vb0']}
vb0 = Resource{char}Position
$active = 1

[Resource{char}Position]
type = Buffer
stride = {STRIDE}
filename = {char}Position.buf
"""
    (preview_dir / f'{char}.ini').write_text(ini, encoding='utf-8')
    print(f"  {char}: vb={face['vb0']} verts={verts} ic={face['ic']} (file vb={face_vb.stat().st_size}B)")
    return True


def main():
    PREVIEW.mkdir(exist_ok=True)
    fails = []
    for c in CHARS:
        if not build_char(c):
            fails.append(c)
    print(f"\n{len(CHARS) - len(fails)}/{len(CHARS)} mods generated")
    if fails:
        for c in fails: print(f"  FAIL: {c}")


if __name__ == '__main__':
    main()
