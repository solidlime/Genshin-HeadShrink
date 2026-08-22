"""make_face_only.py — face メッシュのみ置換する head-shrink mod。

Body / Hair / Accessory 等は元のままで、Face (中規模 IC のペア) のみスケーリング。
IC 6000 前後の中規模ペアを heuristic に face と見なす。

# ponytail: 元の mod (Body + Head) は sub-draw 共有を破壊した可能性。
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
PARSE = ROOT / 'scripts' / 'parse_dump_dir.py'
BUILD = ROOT / 'scripts' / 'build_headshrink_mod.py'
DUMP_BASE = ROOT / 'assets' / 'Dump'
PREVIEW = ROOT / 'assets' / 'Preview'

CHARS = ['Ayaka', 'Chiori', 'Ganyu', 'Keqing C1', 'Kokomi', 'Mizuki', 'Nilou', 'Noelle']
STRIDE = 40

# Shared vb/ib overlay that appears for ALL chars with body-sized IC. Must exclude.
# Body-specific face sub-draws have different hashes (e.g. 49bcaeb1 for Mizuki).
SHARED = {
    'vb0': {'c82fb483'},
    'ib': {'bf1830b6'},
}

DRAW_RE = re.compile(
    r"^(\d+) DrawIndexed\(IndexCount:(\d+),\s*StartIndexLocation:(\d+),\s*BaseVertexLocation:(\d+)\)"
)

# IC range heuristic for face mesh (typically 4000-10000 indices = 1300-3300 tris)
FACE_IC_MIN = 3000
FACE_IC_MAX = 12000


def parse_log(log_path):
    lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
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
        frame = int(m.group(1)); ic = int(m.group(2))
        start = int(m.group(3)); base = int(m.group(4))
        vb_list = sorted(frame_vb.get(frame, set()))
        ib_list = sorted(frame_ib.get(frame, set()))
        if not vb_list or not ib_list: continue
        draws.append({'frame': frame, 'ic': ic, 'start': start, 'base': base,
                      'vb0': vb_list[0], 'ib': ib_list[0]})
    return draws


def find_dump_file(dump_dir, prefix, hash_, frame):
    """Find the specific frame's first dump for hash (e.g. 000NNN-vb0=HASH-*.buf)."""
    pat = f"{frame:06d}-{prefix}={hash_}-*.buf"
    for f in Path(dump_dir).glob(pat):
        return f
    return None


def build_char_face_mod(char):
    dump_dir = DUMP_BASE / char
    preview_dir = PREVIEW / char
    preview_dir.mkdir(parents=True, exist_ok=True)

    log = dump_dir / 'log.txt'
    if not log.exists():
        print(f"[{char}] no log.txt", file=sys.stderr); return False

    draws = parse_log(log)
    # Find face draw: IC 5000-8000 preferred (face sized). Falls back to 3000-12000.
    # Exclude shared overlay hashes (same as build_mod_folders.py).
    candidates = [d for d in draws
                 if d['vb0'] not in SHARED['vb0'] and d['ib'] not in SHARED['ib']
                 and 5000 <= d['ic'] <= 8000]
    if not candidates:
        candidates = [d for d in draws
                     if d['vb0'] not in SHARED['vb0'] and d['ib'] not in SHARED['ib']
                     and FACE_IC_MIN <= d['ic'] <= FACE_IC_MAX]
    if not candidates:
        candidates = [d for d in draws
                     if d['vb0'] not in SHARED['vb0'] and d['ib'] not in SHARED['ib']
                     and 2000 <= d['ic'] <= 15000]
    if not candidates:
        print(f"[{char}] no face candidate", file=sys.stderr); return False
    # Pick largest unique (vb, ib) pair (face is usually mid-large IC, smaller than body)
    pairs = {}
    for d in candidates:
        k = (d['vb0'], d['ib'])
        if k not in pairs or d['ic'] > pairs[k]['ic']:
            pairs[k] = d
    face = sorted(pairs.values(), key=lambda d: d['ic'], reverse=True)[0]

    print(f"\n========== {char} face ==========")
    print(f"  Face: vb={face['vb0']} ib={face['ib']} frame={face['frame']} ic={face['ic']}")

    face_vb = find_dump_file(dump_dir, 'vb0', face['vb0'], face['frame'])
    face_ib = find_dump_file(dump_dir, 'ib', face['ib'], face['frame'])
    if not face_vb or not face_ib:
        print(f"[{char}] dump files missing", file=sys.stderr); return False

    vb_data = face_vb.read_bytes()
    ib_data_full = face_ib.read_bytes()
    actual_ic = min(face['ic'], len(ib_data_full) // 4)
    actual_ic -= actual_ic % 3
    ib_data = ib_data_full[:actual_ic * 4]
    print(f"  face verts={len(vb_data)//STRIDE}, ic={actual_ic} (file {len(ib_data_full)//4})")

    # write scaled face buffers
    verts = len(vb_data) // STRIDE
    pos = bytearray(vb_data)
    # scale all positions by 0.65 around origin (face mesh centered on origin in local space)
    for i in range(verts):
        x, y, z = struct.unpack_from('<3f', pos, i * STRIDE)
        pos[i*STRIDE : i*STRIDE+12] = struct.pack('<3f', x * 0.65, y * 0.65, z * 0.65)

    (preview_dir / 'Position.buf').write_bytes(bytes(pos))
    (preview_dir / 'IB.ib').write_bytes(ib_data)
    (preview_dir / 'hash.json').write_text(json.dumps({
        'position': face['vb0'],
        'ib': face['ib'],
    }, indent=2))

    spec = {
        'vert_count': verts,
        'blend_stride': 0,
        'texcoord_stride': 0,
        'groups': [
            {'name': 'Face', 'vertex_range': [0, verts], 'ib_range': [0, actual_ic]},
        ],
    }
    (preview_dir / 'spec.json').write_text(json.dumps(spec, indent=2))

    res = subprocess.run([
        sys.executable, str(BUILD),
        '--char', char,
        '--dump-dir', str(preview_dir),
        '--output-dir', str(preview_dir),
        '--spec', str(preview_dir / 'spec.json'),
        '--scale', 'Face=0.65,0.65,0.65',
        '--position-stride', str(STRIDE),
        '--index-bytes', '4',
    ], capture_output=True, text=True)
    out_tail = (res.stdout + '\n' + res.stderr).strip().splitlines()[-15:]
    print('\n'.join(out_tail))
    if res.returncode != 0:
        return False
    return True


def main():
    PREVIEW.mkdir(exist_ok=True)
    fails = []
    for c in CHARS:
        if not build_char_face_mod(c):
            fails.append(c)
    print(f"\n========== Summary ==========")
    if fails:
        for c in fails: print(f"  FAIL: {c}")


if __name__ == '__main__':
    main()
