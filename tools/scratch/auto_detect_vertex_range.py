"""auto_detect_vertex_range.py — extract (vertex_range, ib_range) groups from a 3DMigoto frame dump log.

# ponytail: log parser is a state machine over 3 known line shapes; no tokenizer,
# no per-draw object classes. Groups keyed by vb0 hash — same buffer = same part.

Usage:
    python auto_detect_vertex_range.py ^
        --log .\\Mods\\mizuki\\log.txt ^
        [--position-buf .\\Mods\\mizuki\\Position.buf] ^
        [--output .\\groups_spec.json] ^
        [--position-stride 40]

Output is a spec JSON accepted by build_headshrink_mod.py --spec:
    {
      "vert_count": N,
      "groups": [
        {"name": "Part_5c164818", "vertex_range": [s, e], "ib_range": [s, e]},
        ...
      ]
    }

Notes:
    - Non-indexed Draw(...) calls are skipped (no index buffer to split on).
    - A group's vertex_range covers max(BaseVertexLocation+IndexCount) over its
      draws, allocated cumulatively across groups. ib_range is [min StartIndex,
      max StartIndex+IndexCount] of the group's draws.
"""
import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path

DRAW_RE = re.compile(
    r'DrawIndexed\(IndexCount:(\d+), StartIndexLocation:(\d+), BaseVertexLocation:(\d+)\)')
VB0_RE = re.compile(r'^\s*0: resource=0x[0-9a-fA-F]+ hash=([0-9a-fA-F]{8})')
IB_RE = re.compile(r'IASetIndexBuffer\([^)]*\) hash=([0-9a-fA-F]{8})')


def parse_log(text):
    """Extract indexed draws as [{count, start_index, base_vertex, vb0, ib}]."""
    draws = []
    vb0 = None
    ib = None
    for line in text.splitlines():
        m = DRAW_RE.search(line)
        if m:
            draws.append({
                'count': int(m.group(1)),
                'start_index': int(m.group(2)),
                'base_vertex': int(m.group(3)),
                'vb0': vb0,
                'ib': ib,
            })
            continue
        m = VB0_RE.match(line)
        if m:
            vb0 = m.group(1)
            continue
        m = IB_RE.search(line)
        if m:
            ib = m.group(1)
    return draws


def cluster_draws(draws):
    """Group draws by vb0 hash -> OrderedDict[group_name, [draw, ...]]."""
    groups = OrderedDict()
    for d in draws:
        key = d['vb0'] or 'unknown'
        groups.setdefault(f'Part_{key}', []).append(d)
    return groups


def build_spec(groups, vert_count=None):
    """OrderedDict[group -> draws] -> spec dict for build_headshrink_mod.py."""
    out_groups = []
    cursor = 0
    for name, ds in groups.items():
        vspan = max(d['base_vertex'] + d['count'] for d in ds)
        ib_min = min(d['start_index'] for d in ds)
        ib_max = max(d['start_index'] + d['count'] for d in ds)
        out_groups.append({
            'name': name,
            'vertex_range': [cursor, cursor + vspan],
            'ib_range': [ib_min, ib_max],
        })
        cursor += vspan
    if vert_count is None:
        vert_count = cursor
    return {'vert_count': vert_count, 'groups': out_groups}


def auto_detect(log_path, position_buf_path=None, output=None, position_stride=40):
    """Full pipeline: parse -> cluster -> ranges. Returns spec dict."""
    draws = parse_log(Path(log_path).read_text(encoding='utf-8', errors='replace'))
    groups = cluster_draws(draws)
    vert_count = None
    if position_buf_path:
        size = Path(position_buf_path).stat().st_size
        vert_count = size // position_stride
    spec = build_spec(groups, vert_count)
    if output:
        Path(output).write_text(json.dumps(spec, indent=2), encoding='utf-8')
    return spec


def main():
    ap = argparse.ArgumentParser(
        description='Extract vertex/ib ranges per part from a 3DMigoto frame dump log.')
    ap.add_argument('--log', required=True, help='Path to 3DMigoto log.txt')
    ap.add_argument('--position-buf', default=None,
                    help='Optional Position.buf; its size/stride overrides vert_count.')
    ap.add_argument('--output', default=None,
                    help='Output spec JSON (default: <log_dir>/groups_spec.json)')
    ap.add_argument('--position-stride', type=int, default=40)
    args = ap.parse_args()

    out = args.output or str(Path(args.log).with_name('groups_spec.json'))
    spec = auto_detect(args.log, args.position_buf, out, args.position_stride)
    print(f'Spec written: {out}')
    print(f'Groups: {len(spec["groups"])}, vert_count={spec["vert_count"]}')
    for g in spec['groups']:
        print(f'  {g["name"]}: vert {g["vertex_range"]} ib {g["ib_range"]}')


if __name__ == '__main__':
    main()
