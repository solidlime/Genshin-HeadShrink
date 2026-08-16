"""build_mod_folders.py — per-char mod フォルダを assets/Preview/<Char>/ に生成。

ロジック:
- log.txt を parse、全 (vb0, ib) pair を取得
- 全 char 共通の hash = UI overlay (vb0=c82fb483 / ib=bf1830b6) → 除外
- 最大 pair = Body (1.0 維持)、最小 pair = Head (0.65 スケール)
- Body の vb + ib を連結して Position.buf / IB.ib 生成
- hash.json を frame_vb0/frame_ib から作る
- spec.json = { vert_count, groups: [{name, vertex_range, ib_range}, ...] }
- build_headshrink_mod.py で .ini + scaled buf 生成

# ponytail: 最小実装。spec は各 char 手動で tweako できる。
"""
import json
import re
import shutil
import struct
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
PARSE = SCRIPTS / 'parse_dump_dir.py'
BUILD = SCRIPTS / 'build_headshrink_mod.py'

CHARS = ['Ayaka', 'Chiori', 'Ganyu', 'Keqing C1', 'Kokomi', 'Mizuki', 'Nilou', 'Noelle']
DUMP_BASE = ROOT / 'assets' / 'Dump'
SPEC_BASE = ROOT / 'assets' / 'Spec'
PREVIEW = ROOT / 'assets' / 'Preview'

# 共 UI overlay (8 体共通の shared vb/ib hash) — 除外対象
SHARED = {
    'vb0': {'c82fb483'},  # 全 8 char に共通に出現
    'ib': {'bf1830b6'},
}

STRIDE = 40

DRAW_RE = re.compile(
    r"^(\d+) DrawIndexed\(IndexCount:(\d+),\s*StartIndexLocation:(\d+),\s*BaseVertexLocation:(\d+)\)"
)


def parse_log(log_path):
    """Return list of {(vb0, ib), frame, ic, start, base} for all DrawIndexed in log."""
    lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
    # build frame -> {vb0, ib} bindings via Dumping Buffer lines
    frame_vb = defaultdict(set)
    frame_ib = defaultdict(set)
    for ln in lines:
        m = re.match(r"^(\d+) 3DMigoto Dumping Buffer .*-vb0=([0-9a-f]+)", ln)
        if m:
            frame_vb[int(m.group(1))].add(m.group(2)); continue
        m = re.match(r"^(\d+) 3DMigoto Dumping Buffer .*-ib=([0-9a-f]+)", ln)
        if m:
            frame_ib[int(m.group(1))].add(m.group(2))

    draws = []
    for ln in lines:
        m = DRAW_RE.match(ln)
        if not m: continue
        frame = int(m.group(1))
        ic = int(m.group(2))
        start = int(m.group(3))
        base = int(m.group(4))
        vb_list = sorted(frame_vb.get(frame, set()))
        ib_list = sorted(frame_ib.get(frame, set()))
        if not vb_list or not ib_list: continue
        draws.append({
            'frame': frame, 'ic': ic, 'start': start, 'base': base,
            'vb0': vb_list[0], 'ib': ib_list[0],
        })
    return draws


def find_dump_file(dump_dir, prefix, hash_):
    """Find the first 000NNN-<prefix>=<hash>-*.buf in dump_dir."""
    pat = f"[0-9][0-9][0-9][0-9][0-9][0-9]-{prefix}={hash_}-*.buf"
    for f in Path(dump_dir).glob(pat):
        return f
    return None


def build_char_mod(char):
    dump_dir = DUMP_BASE / char
    preview_dir = PREVIEW / char
    preview_dir.mkdir(parents=True, exist_ok=True)

    log = dump_dir / 'log.txt'
    if not log.exists():
        print(f"[{char}] no log.txt", file=sys.stderr); return False

    MIN_IC = 100  # match parse_dump_dir.py default

    draws = parse_log(log)
    # Filter out shared UI overlay + tiny draws
    pairs = defaultdict(list)
    for d in draws:
        if d['ic'] < MIN_IC: continue
        if d['vb0'] in SHARED['vb0'] or d['ib'] in SHARED['ib']: continue
        pairs[(d['vb0'], d['ib'])].append(d)
    if len(pairs) < 2:
        print(f"[{char}] too few non-shared pairs: {len(pairs)}", file=sys.stderr); return False

    # Find max IC pair (Body) and min IC pair (Head, but at least MIN_IC)
    by_ic = {p: max(v, key=lambda x: x['ic']) for p, v in pairs.items()}
    sorted_pairs = sorted(by_ic.values(), key=lambda d: d['ic'], reverse=True)
    body = sorted_pairs[0]
    # pick smallest head (>= MIN_IC already enforced)
    head = sorted_pairs[-1]

    print(f"\n========== {char} ==========")
    print(f"  Body: vb={body['vb0']} ib={body['ib']} frame={body['frame']} ic={body['ic']}")
    print(f"  Head: vb={head['vb0']} ib={head['ib']} frame={head['frame']} ic={head['ic']}")

    # Resolve dump file paths
    body_vb = find_dump_file(dump_dir, 'vb0', body['vb0'])
    body_ib = find_dump_file(dump_dir, 'ib', body['ib'])
    head_vb = find_dump_file(dump_dir, 'vb0', head['vb0'])
    head_ib = find_dump_file(dump_dir, 'ib', head['ib'])
    if not all([body_vb, body_ib, head_vb, head_ib]):
        print(f"[{char}] missing dump files", file=sys.stderr); return False

    # Build merged Position.buf + IB.ib: Body first, Head second, with index adjustment
    body_vb_data = body_vb.read_bytes()
    body_ib_raw = body_ib.read_bytes()
    body_actual_ic = min(body['ic'], len(body_ib_raw) // 4)
    body_actual_ic -= body_actual_ic % 3
    body_ib_data = body_ib_raw[:body_actual_ic * 4]
    print(f"  body ic requested={body['ic']}, file holds={len(body_ib_raw)//4}, using={body_actual_ic}")
    head_vb_data = head_vb.read_bytes()
    head_ib_raw = head_ib.read_bytes()
    head_actual_ic = min(head['ic'], len(head_ib_raw) // 4)
    head_actual_ic -= head_actual_ic % 3
    head_ib_data = head_ib_raw[:head_actual_ic * 4]
    print(f"  head ic requested={head['ic']}, file holds={len(head_ib_raw)//4}, using={head_actual_ic}")

    body_verts = len(body_vb_data) // STRIDE
    head_verts = len(head_vb_data) // STRIDE

    # Adjust head ib indices by +body_verts
    head_indices = struct.unpack(f'<{head_actual_ic}I', head_ib_data)
    head_ib_adj = struct.pack(f'<{head_actual_ic}I', *(i + body_verts for i in head_indices))

    pos = body_vb_data + head_vb_data
    ib = body_ib_data + head_ib_adj

    # Write files
    (preview_dir / 'Position.buf').write_bytes(pos)
    (preview_dir / 'IB.ib').write_bytes(ib)
    (preview_dir / 'hash.json').write_text(json.dumps({
        'position': body['vb0'],  # use body's vb0 hash as Position.buf hash
        'ib': body['ib'],
    }, indent=2))

    spec = {
        'vert_count': body_verts + head_verts,
        'blend_stride': 0,
        'texcoord_stride': 0,
        'groups': [
            {'name': 'Body', 'vertex_range': [0, body_verts], 'ib_range': [0, body_actual_ic]},
            {'name': 'Head', 'vertex_range': [body_verts, body_verts + head_verts],
             'ib_range': [body_actual_ic, body_actual_ic + head_actual_ic]},
        ],
    }
    (preview_dir / 'spec.json').write_text(json.dumps(spec, indent=2))

    # Run build_headshrink_mod.py: HEAD=0.65, BODY=1.0
    res = subprocess.run([
        sys.executable, str(BUILD),
        '--char', char,
        '--dump-dir', str(preview_dir),
        '--output-dir', str(preview_dir),
        '--spec', str(preview_dir / 'spec.json'),
        '--scale', 'Head=0.65,0.65,0.65',
        '--scale', 'Body=1.0,1.0,1.0',
        '--position-stride', str(STRIDE),
        '--index-bytes', '4',
    ], capture_output=True, text=True)
    out_tail = (res.stdout + '\n' + res.stderr).strip().splitlines()[-20:]
    print('\n'.join(out_tail))
    if res.returncode != 0:
        print(f"[{char}] build_headshrink_mod.py failed (rc={res.returncode})", file=sys.stderr)
        return False

    print(f"  → {preview_dir}/  ({sum(f.stat().st_size for f in preview_dir.iterdir())/1024:.0f} KB)")
    return True


def main():
    PREVIEW.mkdir(exist_ok=True)
    fails = []
    for c in CHARS:
        if not build_char_mod(c):
            fails.append(c)
    print(f"\n========== Summary ==========")
    if fails:
        for c in fails: print(f"  FAIL: {c}")
    print(f"{len(CHARS) - len(fails)}/{len(CHARS)} chars built")


if __name__ == '__main__':
    main()
