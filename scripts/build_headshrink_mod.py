"""build_headshrink_mod.py — Build a 3DMigoto mod from dump + scales.

# ponytail: minimal design — read original buffers, scale only position.xyz,
# pass blend/tc through unmodified, split IB at match_first_index boundaries.

Usage:
    python build_headshrink_mod.py ^
        --char Mona ^
        --dump-dir .\\dump\\mona\\ ^
        --output-dir .\\Mods\\Mods\\MonaHeadShrink\\ ^
        --spec .\\groups_spec.mona.json ^
        --scale HEAD=0.65 ^
        --position-stride 40 ^
        --index-bytes 4

Inputs (under dump_dir):
    - Position.buf / VertexBuffer.buf / position.buf  -- vertex buffer
    - IB.ib / IndexBuffer.ib                          -- full index buffer
    - Blend.buf (optional)                            -- bone weights, passthrough
    - TexCoord.buf / UV.buf (optional)                -- UVs, passthrough
    - hash.json                                       -- game-internal buffer hashes

groups_spec.json shape:
    {
      "vert_count": 13855,
      "blend_stride": 32,                  # for .ini only
      "texcoord_stride": 12,
      "groups": [
        {"name":"Head", "vertex_range":[0, 5000],     "ib_range":[0, 17688]},
        {"name":"Body", "vertex_range":[5000, 13855], "ib_range":[17688, 53502]}
      ]
    }

Multiple-unit shape (frame dump direct; index_bytes 2=16bit / 4=32bit):
    {
      "index_bytes": 2,
      "units": [
        {"name": "Body", "position": "def7af36", "ib": "9cf0789e",
         "vert_count": 15965,
         "groups": [{"name":"Head", "vertex_range":[0,4299], "ib_range":[0,12915]}]}
      ]
    }
    Buffers are found in dump_dir by filename: NNNNNN-vb0=<position>-... and
    NNNNNN-ib=<ib>-... (frame dump). Unit name prefixes output filenames.

Scales are specified per group via --scale GROUP=SX,SY,SZ  (omit axis to default all)
"""
import argparse, json, os, struct, sys
from pathlib import Path


def find_buf(dump_dir, candidates):
    """Find first file in dump_dir matching one of the lowercased candidates."""
    files = {f.name.lower(): f for f in Path(dump_dir).iterdir() if f.is_file()}
    for c in candidates:
        if c.lower() in files:
            return files[c.lower()]
    return None


def load_dump(dump_dir):
    """Resolve paths from a dump directory; raise if missing required files."""
    dump_dir = Path(dump_dir)
    pos = find_buf(dump_dir, ['VertexBuffer.buf', 'Position.buf', 'position.buf'])
    ib = find_buf(dump_dir, ['IB.ib', 'IndexBuffer.ib', 'ib.ib', 'IndexBuffer.buf'])
    if pos is None or ib is None:
        raise FileNotFoundError(
            f'dump_dir must contain Position.buf and IB.ib (or matched aliases); '
            f'found pos={pos}, ib={ib}')
    out = {'position': pos, 'ib': ib}
    blend = find_buf(dump_dir, ['Blend.buf', 'blend.buf'])
    if blend:
        out['blend'] = blend
    tc = find_buf(dump_dir, ['TexCoord.buf', 'texcoord.buf', 'UV.buf', 'uv.buf'])
    if tc:
        out['texcoord'] = tc
    hash_path = find_buf(dump_dir, ['hash.json', 'hashes.json'])
    if hash_path is None:
        raise FileNotFoundError('hash.json missing in dump_dir')
    out['hash'] = hash_path
    return out


def parse_hashes(path):
    """hash.json: { "position": "7a1dc890", "blend": "b043715a", ... }"""
    return json.loads(Path(path).read_text(encoding='utf-8'))


def parse_scale(spec_str):
    """'HEAD=0.65' or 'HEAD=0.6,0.6,0.65' -> ('HEAD', (sx,sy,sz))."""
    name, _, val = spec_str.partition('=')
    parts = val.split(',')
    if len(parts) == 1:
        s = float(parts[0])
        return name.strip(), (s, s, s)
    return name.strip(), tuple(float(x) for x in parts)


def bbox_center(buf, stride, indices):
    """Bbox center of selected verts' xyz in float3 space."""
    if not indices:
        return (0.0, 0.0, 0.0)
    xs, ys, zs = [], [], []
    for v in indices:
        x, y, z = struct.unpack_from('<3f', buf, v * stride)
        xs.append(x); ys.append(y); zs.append(z)
    return ((min(xs) + max(xs)) / 2,
            (min(ys) + max(ys)) / 2,
            (min(zs) + max(zs)) / 2)


def scale_positions(buf, stride, indices, scale_xyz, center_xyz):
    """Scale xyz of verts at byte-offsets [v*stride, v*stride+12). Other bytes unchanged."""
    pos = bytearray(buf)
    sx, sy, sz = scale_xyz
    cx, cy, cz = center_xyz
    for v in indices:
        off = v * stride
        x, y, z = struct.unpack_from('<3f', pos, off)
        nx, ny, nz = cx + (x - cx) * sx, cy + (y - cy) * sy, cz + (z - cz) * sz
        struct.pack_into('<3f', pos, off, nx, ny, nz)
    return bytes(pos)


def to_r32_ib(ib, idx_bytes):
    """Repack a 16/32-bit index buffer as uint32 (R32_UINT)."""
    if idx_bytes == 4:
        return ib
    pack_char = 'H' if idx_bytes == 2 else 'I'
    n = len(ib) // idx_bytes
    return struct.pack(f'<{n}I', *struct.unpack(f'<{n}{pack_char}', ib))


def split_ib(ib, idx_bytes, ranges):
    """Split by [(name, start, end)] (index-space) -> {name: bytes}.

    Output is always R32_UINT (uint32 per index), matching the
    [Resource...IB] format = DXGI_FORMAT_R32_UINT declared in the .ini.
    """
    r32 = to_r32_ib(ib, idx_bytes)
    return {n: r32[s * 4:e * 4] for n, s, e in ranges}


def render_ini(char, hashes, vert_count, position_stride, blend_stride,
                texcoord_stride, groups, has_blend, has_texcoord,
                has_ib=True):
    """Build a 3DMigoto .ini section block for one unit. groups:
    [{name, match_first_index, count}].

    Mirrors the proven XXMI/Bennett mod layout (avoids draw freezes): no
    VertexLimitRaise (same-hash double match on one draw), IB override is
    skip-only, part overrides carry match_first_index + explicit
    drawindexed = index count, and all IB resources are
    DXGI_FORMAT_R32_UINT. [Constants] and [Present] are emitted once per
    .ini by the caller (build_units / main), not here.

    has_ib=False omits IB sections/resources (scale-only unit without ib in
    the spec)."""
    has_ib = has_ib and hashes.get('ib') is not None
    L = [f'; {char}\n',
         '; HeadShrink mod — generated by build_headshrink_mod.py\n',
         f'[TextureOverride{char}Position]\n',
         f'hash = {hashes["position"]}\n',
         f'vb0 = Resource{char}Position\n',
         '$active = 1\n\n']
    if has_blend:
        L += [f'[TextureOverride{char}Blend]\n',
              f'hash = {hashes["blend"]}\n',
              'handling = skip\n',
              f'vb1 = Resource{char}Blend\n\n']
    if has_texcoord:
        L += [f'[TextureOverride{char}Texcoord]\n',
              f'hash = {hashes["texcoord"]}\n',
              f'vb1 = Resource{char}Texcoord\n\n']
    if has_ib:
        L += [f'[TextureOverride{char}IB]\n',
              f'hash = {hashes["ib"]}\n',
              'handling = skip\n\n']
        for g in groups:
            L += [f'[TextureOverride{char}{g["name"]}]\n',
                  f'hash = {hashes["ib"]}\n',
                  f'match_first_index = {g["match_first_index"]}\n',
                  f'ib = Resource{char}{g["name"]}IB\n',
                  f'drawindexed = {g["count"]}, 0, 0\n\n']
    # Resources
    L += [f'[Resource{char}Position]\ntype = Buffer\n',
          f'stride = {position_stride}\n',
          f'filename = {char}Position.buf\n\n']
    if has_blend:
        L += [f'[Resource{char}Blend]\ntype = Buffer\n',
              f'stride = {blend_stride}\n',
              f'filename = {char}Blend.buf\n\n']
    if has_texcoord:
        L += [f'[Resource{char}Texcoord]\ntype = Buffer\n',
              f'stride = {texcoord_stride}\n',
              f'filename = {char}Texcoord.buf\n\n']
    if has_ib:
        for g in groups:
            L += [f'[Resource{char}{g["name"]}IB]\n',
                  'type = Buffer\n',
                  'format = DXGI_FORMAT_R32_UINT\n',
                  f'filename = {char}{g["name"]}.ib\n\n']
    return ''.join(L)


INI_HEADER = '[Constants]\nglobal $active = 0\n\n'
INI_FOOTER = '[Present]\npost $active = 0\n'


def find_dump_hash(dump_dir, prefix, hashval):
    """Find a frame-dump file whose name contains '<prefix><hashval>'.

    e.g. find_dump_hash(dir, 'vb0=', 'def7af36') matches
    '000037-vb0=def7af36-vs=...-ps=....buf'. Same hash may appear in several
    frames; any copy works (identical content).
    """
    token = prefix + hashval
    for f in Path(dump_dir).rglob('*.buf'):
        if token in f.name:
            return f
    return None


def build_units(args, spec):
    """Multiple-unit path: each unit is one (vb0, ib) dump pair.

    Buffers are resolved per unit: frame-dump filenames (NNNNNN-vb0=<hash>...
    .buf / NNNNNN-ib=<hash>....buf) first, then legacy aliases
    (Position.buf / IB.ib / hash.json). 'ib', 'blend' and 'texcoord' keys are
    optional — omitted buffers are skipped (scale-only units).
    """
    index_bytes = spec.get('index_bytes', args.index_bytes)
    dump_dir = Path(args.dump_dir)
    scales = dict(parse_scale(s) for s in args.scale)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ini_parts = [INI_HEADER]
    for unit in spec['units']:
        prefix = args.char + (unit.get('name') or '')
        pos_file = find_dump_hash(dump_dir, 'vb0=', unit['position'])
        if pos_file is None:
            pos_file = find_buf(dump_dir, ['VertexBuffer.buf', 'Position.buf'])
        if pos_file is None:
            raise FileNotFoundError(
                f"unit '{unit.get('name', '')}': vb0={unit['position']} "
                f'not found under {dump_dir}')
        ib_file = None
        if unit.get('ib'):
            ib_file = find_dump_hash(dump_dir, 'ib=', unit['ib'])
            if ib_file is None:
                ib_file = find_buf(
                    dump_dir, ['IB.ib', 'IndexBuffer.ib', 'IndexBuffer.buf'])
            if ib_file is None:
                raise FileNotFoundError(
                    f"unit '{unit.get('name', '')}': "
                    f"ib={unit['ib']} not found under {dump_dir}")
        blend_file = None
        if unit.get('blend'):
            blend_file = find_dump_hash(dump_dir, 'vb1=', unit['blend'])
            if blend_file is None:
                blend_file = find_buf(dump_dir, ['Blend.buf'])
            if blend_file is None:
                raise FileNotFoundError(
                    f"unit '{unit.get('name', '')}': "
                    f"blend={unit['blend']} not found under {dump_dir}")
        tc_file = None
        if unit.get('texcoord'):
            tc_file = find_dump_hash(dump_dir, 'vb2=', unit['texcoord'])
            if tc_file is None:
                tc_file = find_buf(
                    dump_dir, ['TexCoord.buf', 'UV.buf'])
            if tc_file is None:
                raise FileNotFoundError(
                    f"unit '{unit.get('name', '')}': "
                    f"texcoord={unit['texcoord']} not found under {dump_dir}")

        pos_data = pos_file.read_bytes()
        # Apply scales (vertex ranges are within this unit's VB).
        scaled_pos = pos_data
        for grp in unit['groups']:
            if grp['name'] not in scales:
                continue
            s_xyz = scales[grp['name']]
            v_start, v_end = grp['vertex_range']
            indices = list(range(v_start, v_end))
            center = bbox_center(pos_data, args.position_stride, indices)
            scaled_pos = scale_positions(
                scaled_pos, args.position_stride, indices, s_xyz, center)
        # Write unit outputs.
        (out / f'{prefix}Position.buf').write_bytes(scaled_pos)
        hashes = {'position': unit['position'],
                  'vertex_limit': unit['position']}
        ini_groups = []
        if ib_file is not None:
            ib_data = ib_file.read_bytes()
            hashes['ib'] = unit['ib']
            r32 = to_r32_ib(ib_data, index_bytes)
            for grp in unit['groups']:
                s, e = grp['ib_range']
                (out / f'{prefix}{grp["name"]}.ib').write_bytes(
                    r32[s * 4:e * 4])
                ini_groups.append(
                    {'name': grp['name'], 'match_first_index': s,
                     'count': e - s})
        has_blend = blend_file is not None
        if blend_file is not None:
            hashes['blend'] = unit['blend']
            (out / f'{prefix}Blend.buf').write_bytes(blend_file.read_bytes())
        has_texcoord = tc_file is not None
        if tc_file is not None:
            hashes['texcoord'] = unit['texcoord']
            (out / f'{prefix}Texcoord.buf').write_bytes(tc_file.read_bytes())
        unit_blend_stride = unit.get('blend_stride', args.blend_stride)
        ini_parts.append(render_ini(
            prefix, hashes, unit['vert_count'], args.position_stride,
            unit_blend_stride, args.texcoord_stride, ini_groups,
            has_blend, has_texcoord,
            has_ib=ib_file is not None))
    ini_parts.append(INI_FOOTER)
    (out / f'{args.char}.ini').write_text('\n'.join(ini_parts), encoding='utf-8')
    print(f'Mod folder: {out}')


def main():
    ap = argparse.ArgumentParser(
        description='Build a 3DMigoto mod from dump + scales (position-only modifier).')
    ap.add_argument('--char', required=True)
    ap.add_argument('--dump-dir', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--spec', required=True,
                    help='Group spec JSON (see module docstring).')
    ap.add_argument('--scale', action='append', default=[],
                    help='Scale directive GROUP=SX,SY,SZ. Repeatable.')
    ap.add_argument('--position-stride', type=int, default=40)
    ap.add_argument('--index-bytes', type=int, default=4)
    ap.add_argument('--blend-stride', type=int, default=32)
    ap.add_argument('--texcoord-stride', type=int, default=12)
    ap.add_argument('--dry-run', action='store_true',
                    help='Validate spec only; skip dump reading.')
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding='utf-8'))
    if 'units' in spec:
        if args.dry_run:
            n = sum(len(u['groups']) for u in spec['units'])
            print(f'Dry run OK: {len(spec["units"])} units, {n} groups')
            return
        build_units(args, spec)
        return
    vert_count = spec['vert_count']
    groups = spec['groups']
    if args.dry_run:
        print(f'Dry run OK: {len(groups)} groups, vert_count={vert_count}')
        return

    bufs = load_dump(args.dump_dir)
    pos_data = Path(bufs['position']).read_bytes()
    ib_data = Path(bufs['ib']).read_bytes()
    blend_data = Path(bufs['blend']).read_bytes() if 'blend' in bufs else None
    tc_data = Path(bufs['texcoord']).read_bytes() if 'texcoord' in bufs else None
    hashes = parse_hashes(bufs['hash'])

    scales = dict(parse_scale(s) for s in args.scale)

    # Apply scales.
    scaled_pos = pos_data
    for grp in groups:
        if grp['name'] not in scales:
            continue
        s_xyz = scales[grp['name']]
        v_start, v_end = grp['vertex_range']
        indices = list(range(v_start, v_end))
        center = bbox_center(pos_data, args.position_stride, indices)
        scaled_pos = scale_positions(
            scaled_pos, args.position_stride, indices, s_xyz, center)

    # Split IB.
    ib_groups = [(g['name'], g['ib_range'][0], g['ib_range'][1]) for g in groups]
    ibs = split_ib(ib_data, args.index_bytes, ib_groups)

    # Write outputs.
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f'{args.char}Position.buf').write_bytes(scaled_pos)
    if blend_data:
        (out / f'{args.char}Blend.buf').write_bytes(blend_data)
    if tc_data:
        (out / f'{args.char}Texcoord.buf').write_bytes(tc_data)
    for nm, data in ibs.items():
        (out / f'{args.char}{nm}.ib').write_bytes(data)

    # .ini
    ini_groups = [
        {'name': g['name'],
         'match_first_index': g['ib_range'][0],
         'count': g['ib_range'][1] - g['ib_range'][0]}
        for g in groups
    ]
    ini = INI_HEADER + render_ini(args.char, hashes, vert_count,
                                  args.position_stride,
                                  args.blend_stride, args.texcoord_stride,
                                  ini_groups, blend_data is not None,
                                  tc_data is not None) + INI_FOOTER
    (out / f'{args.char}.ini').write_text(ini, encoding='utf-8')
    print(f'Mod folder: {out}')


if __name__ == '__main__':
    main()
