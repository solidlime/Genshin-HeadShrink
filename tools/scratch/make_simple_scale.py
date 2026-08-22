"""make_simple_scale.py — 単一 vb を単一 scale で置き換える最小 mod。

使い方: python make_simple_scale.py <char> <vb_hash> <scale> <out_name>
例: Mizuki で face vb (49bcaeb1) を 0.65 倍 → assets/Preview/Mizuki/MizukiFaceScale/

# ponytail: 最小構成。複数 hash を順に試して freeze 切り分け用。
"""
import argparse
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
STRIDE = 40
DRAW_RE = re.compile(
    r"^(\d+) DrawIndexed\(IndexCount:(\d+),\s*StartIndexLocation:(\d+),\s*BaseVertexLocation:(\d+)\)"
)


def find_target_frame(dump_dir, vb_hash):
    """Find the FIRST frame in dump dir that uses vb_hash, return (frame, ic, ib_hash)."""
    log = dump_dir / 'log.txt'
    frame_vb = defaultdict(set); frame_ib = defaultdict(set)
    for ln in log.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r"^(\d+) 3DMigoto Dumping Buffer .*-vb0=([0-9a-f]+)", ln)
        if m: frame_vb[int(m.group(1))].add(m.group(2)); continue
        m = re.match(r"^(\d+) 3DMigoto Dumping Buffer .*-ib=([0-9a-f]+)", ln)
        if m: frame_ib[int(m.group(1))].add(m.group(2))
    draws = []
    for ln in log.read_text(encoding='utf-8', errors='replace').splitlines():
        m = DRAW_RE.match(ln)
        if not m: continue
        frame = int(m.group(1)); ic = int(m.group(2))
        vb_list = sorted(frame_vb.get(frame, set()))
        ib_list = sorted(frame_ib.get(frame, set()))
        if vb_hash in vb_list:
            for d in draws:
                if d['frame'] == frame and d['vb0'] == vb_hash and d['ic'] >= ic:
                    d['ic'] = ic; d['ib'] = ib_list[0] if ib_list else d['ib']; break
            else:
                draws.append({'frame': frame, 'ic': ic, 'vb0': vb_hash,
                              'ib': ib_list[0] if ib_list else None})
    if not draws:
        return None
    # pick draw with max IC for that vb hash
    return max(draws, key=lambda d: d['ic'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('char')
    ap.add_argument('vb_hash')
    ap.add_argument('scale', type=float)
    ap.add_argument('out_name')
    args = ap.parse_args()

    char = args.char
    vb_hash = args.vb_hash
    scale = args.scale
    out_name = args.out_name

    dump_dir = DUMP_BASE / char
    preview_dir = PREVIEW / out_name
    preview_dir.mkdir(parents=True, exist_ok=True)

    target = find_target_frame(dump_dir, vb_hash)
    if not target:
        print(f"FAIL: vb {vb_hash} not in {char} dump", file=sys.stderr); sys.exit(1)
    print(f"Target draw: char={char} vb={vb_hash} ib={target['ib']} frame={target['frame']} ic={target['ic']}")

    # locate vb file
    pat = f"{target['frame']:06d}-vb0={vb_hash}-*.buf"
    vb_file = next(iter(dump_dir.glob(pat)), None)
    if not vb_file:
        print(f"FAIL: no vb file for {vb_hash}", file=sys.stderr); sys.exit(1)

    # Scale positions, leave rest intact
    vb_data = bytearray(vb_file.read_bytes())
    verts = len(vb_data) // STRIDE
    for i in range(verts):
        x, y, z = struct.unpack_from('<3f', vb_data, i * STRIDE)
        vb_data[i*STRIDE : i*STRIDE+12] = struct.pack('<3f', x * scale, y * scale, z * scale)

    (preview_dir / f'{out_name}Position.buf').write_bytes(bytes(vb_data))
    (preview_dir / 'hash.json').write_text(json.dumps({'position': vb_hash}, indent=2))

    ini = f"""\
; {out_name} — head shrink (scale {scale}) for {char}
; Single VB override. Game uses original IB & resources.

[TextureOverride{out_name}Position]
hash = {vb_hash}
vb0 = Resource{out_name}Position
$active = 1

[Resource{out_name}Position]
type = Buffer
stride = {STRIDE}
filename = {out_name}Position.buf
"""
    (preview_dir / f'{out_name}.ini').write_text(ini, encoding='utf-8')
    print(f"Wrote {preview_dir}/")
    print(f"  scale={scale} verts={verts} size={len(vb_data)}")


if __name__ == '__main__':
    main()
