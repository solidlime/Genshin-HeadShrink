"""HeadShrink Blender Add-on
Direct 3DMigoto dump import, whole-body preview shrink, and CopyDispatch
diff-mod export (Base/Key buffers + HLSL + INI) — all inside Blender.

Flow: Dump Import -> Preview Adjust -> Mod Export.

Install: Edit -> Preferences -> Add-ons -> Install this .py
Use: N-panel -> "HeadShrink" tab
"""
bl_info = {
    "name": "HeadShrink",
    "author": "herta",
    "version": (1, 6, 6),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > HeadShrink",
    "description": "Dump import + preview shrink + CopyDispatch diff-mod export",
    "category": "Object",
}

import json
import math
import os
import re
import struct

try:
    import bpy
except ImportError:  # headless import (unit tests / py_compile)
    bpy = None  # type: ignore[assignment]

# ===== CONSTANTS =====
DUMP_STRIDE = 40                    # Genshin standard position stride (float3 at offset 0)
DUMP_INDEX_BYTES = 2                # 16-bit IB only (R16_UINT)
DUMP_COLLECTION = "HeadShrink_Dump"



# ===== DUMP PIPELINE (bpy-independent) =====
_DUMP_FRAME_RE = re.compile(r'^(\d+)-vb0=([0-9a-fA-F]+)')
_DUMP_IB_RE = re.compile(r'^(\d+)-ib=([0-9a-fA-F]+)')


def scan_dump_dir(dump_dir):
    """Scan a 3DMigoto frame dump dir -> list of (vb0, ib) pairs.

    Pairs files 'NNNNNN-vb0=<hash>-...' with 'NNNNNN-ib=<hash>-...' sharing the
    same frame number. vert_count/index_count are derived from file sizes
    (stride 40 / 16-bit). Same (vb0, ib) hash pair seen in several frames is
    deduped (identical content).
    """
    try:
        names = os.listdir(dump_dir)
    except OSError:
        return []
    by_frame = {}
    for fn in names:
        m = _DUMP_FRAME_RE.match(fn)
        if m:
            by_frame.setdefault(m.group(1), {})['vb0'] = (
                m.group(2).lower(), os.path.join(dump_dir, fn))
            continue
        m = _DUMP_IB_RE.match(fn)
        if m:
            by_frame.setdefault(m.group(1), {})['ib'] = (
                m.group(2).lower(), os.path.join(dump_dir, fn))
    seen, out = set(), []
    for frame in sorted(by_frame):
        pair = by_frame[frame]
        if 'vb0' not in pair or 'ib' not in pair:
            continue
        key = (pair['vb0'][0], pair['ib'][0])
        if key in seen:
            continue
        seen.add(key)
        vb0_hash, vb0_path = pair['vb0']
        ib_hash, ib_path = pair['ib']
        out.append({
            'vb0': vb0_hash, 'ib': ib_hash, 'frame': frame,
            'vert_count': os.path.getsize(vb0_path) // DUMP_STRIDE,
            'index_count': os.path.getsize(ib_path) // DUMP_INDEX_BYTES,
            'vb0_path': vb0_path, 'ib_path': ib_path,
        })
    return out


# --- Coordinate systems -----------------------------------------------------
# Genshin game space: x+ = down (head x~0, feet x~1.0), y = lateral, z = depth.
# Blender display uses z+ = up. game_to_display = rotation +90deg about Y:
#   (x, y, z)_game -> (z, y, -x)_display, and display_to_game is its inverse.
# The transform is character-independent, so it applies to every dump.
def game_to_display(p):
    """Game (x=down) -> display (z=up): (p.z, p.y, -p.x)."""
    return (p[2], p[1], -p[0])


def display_to_game(p):
    """Display (z=up) -> game (x=down): (-p.z, p.y, p.x)."""
    return (-p[2], p[1], p[0])


def preview_shrink_mesh(mesh, center, half, scale, offset=(0.0, 0.0, 0.0),
                        falloff=0.0, shift=(0.0, 0.0, 0.0), all_verts=False,
                        origin=None):
    """Recompute vertex coords from hs_original_pos (non-accumulating).

    Shrink-box test and scaling happen in display space (vertex + object
    offset); results are written back in local coordinates. offset=(0,0,0)
    behaves exactly like plain local-space shrinking. all_verts=True skips
    the box test (uniform shrink+shift over the whole mesh). origin is the
    scale pivot in display coords (see shrink_positions); None keeps the
    legacy pivot = center. Returns True when applied; False when the mesh
    has no hs_original_pos attribute.
    """
    attr = mesh.attributes.get('hs_original_pos')
    if attr is None:
        return False
    n = len(mesh.vertices)
    flat = [0.0] * (n * 3)
    attr.data.foreach_get('vector', flat)
    base = [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]
    show = [(p[0] + offset[0], p[1] + offset[1], p[2] + offset[2]) for p in base]
    moved = shrink_positions(show, center, half, scale, falloff, shift,
                             all_verts, origin)
    for v, p in enumerate(moved):
        mesh.vertices[v].co = (p[0] - offset[0], p[1] - offset[1],
                               p[2] - offset[2])
    mesh.update()
    return True


def is_body_mesh(ob, meshes):
    """True when ob is the main body: the mesh with the most vertices.

    Ties count as body (not smaller than any sibling). Empty 'meshes' -> False.
    """
    if not meshes:
        return False
    n = len(ob.data.vertices)
    return all(n >= len(m.data.vertices) for m in meshes)


def head_center_from_verts(verts, fraction=0.25):
    """Center of the highest 'fraction' of vertices along z (display coords).

    Used to auto-place shared face units onto the main body's head. Returns
    None for empty input or when no finite vertex remains (NaN/inf guard).
    """
    if not verts:
        return None
    finite = [v for v in verts if all(math.isfinite(c) for c in v)]
    if not finite:
        return None
    zs = sorted(v[2] for v in finite)
    threshold = zs[max(0, int(len(zs) * (1 - fraction)) - 1)]
    sel = [v for v in finite if v[2] >= threshold]
    return tuple(sum(p[i] for p in sel) / len(sel) for i in range(3))


def load_dump_mesh(vb0_path, ib_path, stride=DUMP_STRIDE):
    """Read a stride-40 vb0 + 16-bit ib -> (verts, faces, max_index).

    Faces follow IB order (3 indices per triangle). Vertices are returned in
    display coordinates (game_to_display applied). Raises ValueError on odd
    IB size (not 16-bit) or when max index exceeds vert_count (likely 32-bit).
    """
    with open(vb0_path, 'rb') as f:
        vb = f.read()
    with open(ib_path, 'rb') as f:
        ib = f.read()
    if len(ib) % 2:
        raise ValueError(f'IB size {len(ib)} is odd; expected 16-bit indices')
    index_count = len(ib) // 2
    vert_count = len(vb) // stride
    verts = [game_to_display(struct.unpack_from('<3f', vb, i * stride))
             for i in range(vert_count)]
    idx = struct.unpack('<%dH' % index_count, ib)
    max_index = max(idx) if idx else 0
    if max_index >= vert_count:
        raise ValueError(
            f'max index {max_index} >= vert_count {vert_count}; '
            f'IB is likely 32-bit (unsupported, 16-bit only)')
    faces = [tuple(idx[i:i + 3]) for i in range(0, index_count - 2, 3)]
    return verts, faces, max_index


# ===== PREVIEW & COPYDISPATCH DIFF =====
PREVIEW_COLLECTION = "HS_Preview"
SHRINK_BOX_NAME = "HS_ShrinkBox"
_ROLE_TO_UNIT_NAME = {
    'BODY': 'Body',
    'EYES': 'Eyes',
    'MOUTH': 'Mouth',
    'BROW': 'Brow',
}
DIFF_HLSL = """struct vb0 { float3 position; float3 normal; float4 tangent; };
RWStructuredBuffer<vb0> rw_buffer : register(u1);
StructuredBuffer<vb0> base : register(t0);
StructuredBuffer<vb0> key : register(t1);
[numthreads(1, 1, 1)]
void main(uint3 DTid : SV_DispatchThreadID) {
    rw_buffer[DTid.x].position += key[DTid.x].position - base[DTid.x].position;
}
"""


def unit_name_for_role(role, vb0_hash):
    """Map a unit role (BODY/EYES/MOUTH/BROW/OTHER) to its diff unit name.

    Roles are per-character data (see save_char_config); unknown roles fall
    back to Unit<hash8> so any dumped mesh still gets a usable name.
    """
    return _ROLE_TO_UNIT_NAME.get(str(role), 'Unit' + str(vb0_hash)[:8])


def role_for_pair(vb0, vert_count, units_map, is_largest):
    """Resolve the hs_role for a dumped pair.

    units_map (per-character {vb0_hash: role}) wins when it knows the hash;
    otherwise the largest mesh is the body (BODY) and everything else is
    OTHER until the user re-tags it (or the char config is saved).
    """
    if units_map and str(vb0) in units_map:
        return units_map[str(vb0)]
    return 'BODY' if is_largest else 'OTHER'


def in_shrink_box(pos, center, half):
    """True if pos lies inside the axis-aligned shrink box [center-half, center+half]."""
    return all(abs(pos[i] - center[i]) <= half[i] for i in range(3))


def eye_region_bboxes(meshes):
    """Display-space bboxes of every EYES-role mesh in a mesh object list.

    meshes: sequence of bpy mesh objects (HS_Preview objects). Each EYES-role
    mesh (obj.get('hs_role') == 'EYES') contributes one bbox
    ((min_x, min_y, min_z), (max_x, max_y, max_z)) computed from display
    coords (v.co + obj.location; scale/rotation assumed identity). Returns []
    when no EYES-role mesh is present.
    """
    boxes = []
    for obj in meshes:
        if not (obj.type == 'MESH' and obj.get('hs_role') == 'EYES'):
            continue
        loc = tuple(obj.location)
        verts = [(v.co[0] + loc[0], v.co[1] + loc[1], v.co[2] + loc[2])
                 for v in obj.data.vertices]
        if not verts:
            continue
        bmin = tuple(min(c[i] for c in verts) for i in range(3))
        bmax = tuple(max(c[i] for c in verts) for i in range(3))
        boxes.append((bmin, bmax))
    return boxes


def eye_sink_positions(verts, eye_bboxes, pad, sink):
    """Sink head verts in the eyes region back along x (display coords).

    verts: sequence of display-space positions (Vector or 3-sequence).
    eye_bboxes: list of (bmin, bmax) bboxes (display space, location-
    inclusive). A vert is in the region when, for at least one bbox,
    y in [bmin.y-pad, bmax.y+pad] and z in [bmin.z-pad, bmax.z+pad] and
    x <= bmax.x+pad. In-region verts move to (x - sink, y, z); everything
    else is unchanged. sink <= 0 short-circuits to the input unchanged
    (fast path). Returns a new list; never mutates the input.
    """
    if sink <= 0.0 or not verts or not eye_bboxes:
        return list(verts)
    ranges = []
    for bmin, bmax in eye_bboxes:
        ranges.append((bmin[1] - pad, bmax[1] + pad,
                       bmin[2] - pad, bmax[2] + pad,
                       bmax[0] + pad))
    out = []
    for p in verts:
        hit = False
        for y0, y1, z0, z1, x_max in ranges:
            if y0 <= p[1] <= y1 and z0 <= p[2] <= z1 and p[0] <= x_max:
                hit = True
                break
        if hit:
            out.append((p[0] - sink, p[1], p[2]))
        else:
            out.append(p)
    return out


def resolve_eye_bboxes(eye_bboxes, region_min, region_max):
    """Pick the eye-region bbox list: user override or automatic detection.

    A user-set region (both eye_region_min and eye_region_max non-zero, i.e.
    neither is all-zeros) wins over the automatic EYES-mesh bboxes and is
    returned as a single-bbox list. When either endpoint is None or both are
    (0,0,0), the automatic list is returned unchanged. Never mutates input.
    """
    if region_min is None or region_max is None:
        return eye_bboxes
    if not any(region_min) and not any(region_max):
        return eye_bboxes
    return [(tuple(region_min), tuple(region_max))]


def selection_display_bbox(mesh, vert_indices, offset):
    """Display-space bbox ((bmin, bmax)) of the chosen mesh vertices.

    mesh: object with a .vertices sequence (bpy mesh or test stub); each
    selected vertex's local co is offset by 'offset' (object location) to
    match eye_region_bboxes()'s display-space convention. Returns None for
    an empty selection.
    """
    idx = list(vert_indices)
    if not idx:
        return None
    loc = tuple(offset)
    verts = [(mesh.vertices[i].co[0] + loc[0],
              mesh.vertices[i].co[1] + loc[1],
              mesh.vertices[i].co[2] + loc[2]) for i in idx]
    bmin = tuple(min(c[j] for c in verts) for j in range(3))
    bmax = tuple(max(c[j] for c in verts) for j in range(3))
    return (bmin, bmax)


def shrink_positions(verts, center, half, scale, falloff=0.0,
                     shift=(0.0, 0.0, 0.0), all_verts=False, origin=None):
    """[(x,y,z)...] -> [(x',y',z')...] with a smooth boundary fade.

    In-box verts (normalized distance d <= 1) scale about the pivot by 'scale'
    and translate by 'shift' (full strength). A band of width 'falloff' *
    box size beyond the surface linearly blends the factor back to 1.0, so
    nothing jumps at the boundary; the shift fades to 0 the same way (so
    neighboring geometry is not torn apart). falloff=0.0 and shift=(0,0,0)
    keep the legacy behavior exactly (in-box scaled, outside unchanged).
    Axes with half[i] == 0 are excluded from the distance so a zero-thickness
    axis never disables the fade (and never divides by zero).

    origin is the scale pivot, decoupled from the box position: the box test
    (d vs center/half) picks WHICH vertices transform, while scaling happens
    about 'origin'. origin=None keeps the legacy pivot = center. Typical use:
    box centered on the head, origin at the neck so the head shrinks toward
    the neck without drifting.

    all_verts=True skips the box test entirely: every vertex maps to
    origin + (p - origin) * scale + shift (uniform shrink+shift). Used for
    small standalone face meshes so the whole part moves as one and no
    seams/tears appear between parts. half/falloff are ignored in that mode.
    """
    pivot = origin if origin is not None else center
    if all_verts:
        return [tuple(pivot[i] + (p[i] - pivot[i]) * scale + shift[i]
                      for i in range(3)) for p in verts]
    out = []
    for p in verts:
        axes = [i for i in range(3) if half[i] > 0]
        if axes:
            d = max(abs(p[i] - center[i]) / half[i] for i in axes)
        else:  # collapsed box: legacy behavior keeps everything in place
            d = float('inf')
        if d <= 1.0:
            s, t = scale, 1.0
        elif falloff > 0.0 and d <= 1.0 + falloff:
            t = (d - 1.0) / falloff
            s = scale + (1.0 - scale) * t
            t = 1.0 - t  # shift fades to 0 across the band
        else:
            s, t = 1.0, 0.0
        if s == 1.0 and t == 0.0:
            out.append(tuple(p))
        else:
            out.append(tuple(pivot[i] + (p[i] - pivot[i]) * s + shift[i] * t
                             for i in range(3)))
    return out


def replace_positions(base_data, new_verts, stride=DUMP_STRIDE):
    """Copy base VB bytes, overwrite only each vertex's position float3 (normal/tangent kept)."""
    out = bytearray(base_data)
    for v, p in enumerate(new_verts):
        struct.pack_into('<3f', out, v * stride, *p)
    return bytes(out)


# ===== SHRINK BOX WIREFRAME (bpy-independent) =====
def box_wireframe_verts(center, half):
    """8 corners of the axis-aligned box (center ± half per axis), display coords."""
    cx, cy, cz = center
    hx, hy, hz = half
    return [
        (cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),
        (cx - hx, cy + hy, cz - hz), (cx + hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
        (cx - hx, cy + hy, cz + hz), (cx + hx, cy + hy, cz + hz),
    ]


def box_wireframe_edges():
    """12 edges of the box (vertex index pairs)."""
    return [
        (0, 1), (2, 3), (0, 2), (1, 3),   # bottom face
        (4, 5), (6, 7), (4, 6), (5, 7),   # top face
        (0, 4), (1, 5), (2, 6), (3, 7),   # vertical struts
    ]


def bbox_center(verts):
    """Center of the axis-aligned bounding box of verts; None when empty."""
    if not verts:
        return None
    return tuple((min(p[i] for p in verts) + max(p[i] for p in verts)) / 2.0
                 for i in range(3))


def box_center_from_obj(obj):
    """World-space bbox center of a mesh object (local vert bbox + location)."""
    local = bbox_center([tuple(v.co) for v in obj.data.vertices])
    if local is None:
        return None
    loc = obj.location
    return tuple(local[i] + loc[i] for i in range(3))


def build_diff_ini(char, units):
    """units: [{name(char+Unit), vb_hash, vert_count}] -> CopyDispatch ini text.

    TextureOverride switches the vb0 hash to a CommandList that copies the
    original VB into Resource<name>Dif, runs CustomShader<name> (delta =
    key - base per vertex), then copies the result back over the original.
    """
    parts = ["[Constants]", "global $active = 0", "", "[Present]", "post $active = 0", ""]
    for u in units:
        n = u['name']
        parts += [
            f"[TextureOverride{n}]",
            f"hash = {u['vb_hash']}",
            "$active = 1",
            f"run = CommandList{n}",
            "",
            f"[CommandList{n}]",
            f"Resource{n}Dif = copy this",
            f"run = CustomShader{n}",
            f"this = Resource{n}Dif",
            "",
            f"[Resource{n}Dif]",
            "",
            f"[Resource{n}Base]",
            "type = RWBuffer",
            f"stride = {DUMP_STRIDE}",
            f"filename = {n}Base.buf",
            "",
            f"[Resource{n}Key]",
            "type = RWBuffer",
            f"stride = {DUMP_STRIDE}",
            f"filename = {n}Key.buf",
            "",
            f"[CustomShader{n}]",
            f"cs = {char}Head.hlsl",
            "",
            f"cs-u1 = copy Resource{n}Dif",
            f"cs-t0 = copy Resource{n}Base",
            f"cs-t1 = copy Resource{n}Key",
            "",
            f"Dispatch = {u['vert_count']}, 1, 1",
            f"Resource{n}Dif = copy cs-u1",
            "post cs-u1 = null",
            "",
        ]
    return "\n".join(parts)


FACE_OFFSETS_FILE = 'face_offsets.json'
DEFAULT_CONFIG_KEY = '__default__'  # shared per-char fallback config entry


def face_offsets_path():
    """Path to the per-character face-offset store (script dir; cwd fallback).

    Blender may exec the addon without __file__ defined, so guard it.
    """
    try:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            FACE_OFFSETS_FILE)
    except NameError:
        return os.path.join(os.getcwd(), FACE_OFFSETS_FILE)


def load_face_offsets(path, char_name):
    """{obj_name: [x,y,z]} for char_name; {} on missing/corrupt file or unknown char."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    entry = data.get(char_name)
    if not isinstance(entry, dict):
        return {}
    out = {}
    for name, loc in entry.items():
        if isinstance(name, str) and isinstance(loc, list) and len(loc) == 3:
            try:
                out[name] = [float(v) for v in loc]
            except (TypeError, ValueError):
                continue
    return out


def save_face_offsets(path, char_name, locations):
    """Merge {obj_name: [x,y,z]} under char_name; returns number of entries saved."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    rounded = {k: [round(float(v[i]), 6) for i in range(3)]
               for k, v in locations.items()}
    data[char_name] = rounded
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return len(rounded)


def save_char_config(path, char_name, locations, config):
    """Merge face offsets + a per-character config dict under char_name.

    Locations go in as plain entries, the shrink/role config under
    '__config__' inside the same char_name entry, so one file holds both.
    Returns the number of face-offset entries saved.
    """
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    entry = data.get(char_name)
    if not isinstance(entry, dict):
        entry = {}
    for k, v in locations.items():
        entry[k] = [round(float(v[i]), 6) for i in range(3)]
    entry['__config__'] = config
    data[char_name] = entry
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return len(locations)


def load_char_config(path, char_name):
    """Config dict for char_name (or {} when absent / legacy / corrupt).

    Legacy files written by save_face_offsets have no '__config__' key and
    load as {} — old data stays readable via load_face_offsets.
    """
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    entry = data.get(char_name)
    if not isinstance(entry, dict):
        return {}
    cfg = entry.get('__config__')
    return cfg if isinstance(cfg, dict) else {}


def _has_registered_units(char_name):
    """キャラの units (vb0->role) が登録済みか (__config__.units が非空 dict)。

    auto_setup の自動発火 (dump_dir 変更時) の条件に使う。units 未登録なら
    キャラメッシュの判別ができないため、自動実行せず手動ボタンに委ねる。
    """
    units = load_char_config(face_offsets_path(), char_name).get('units')
    return isinstance(units, dict) and bool(units)


def resolve_char_config(path, char_name):
    """Merged config: shared __default__ base + per-character overrides.

    The default entry fills every key, the char entry wins on conflicts.
    Returns {} when neither exists. load_char_config is untouched.
    """
    cfg = load_char_config(path, DEFAULT_CONFIG_KEY)
    cfg.update(load_char_config(path, char_name))
    return cfg


def extract_char_config(props):
    """Serialize the current shrink/pupil/face props into a plain dict.

    FloatVector props become lists (JSON-friendly). 'units' (vb0->role) is
    filled in by the caller from the imported meshes.
    """
    return {
        'shrink_center': [float(v) for v in props.shrink_center],
        'shrink_origin': [float(v) for v in props.shrink_origin],
        'shrink_half': [float(v) for v in props.shrink_half],
        'shrink_scale': float(props.shrink_scale),
        'shrink_falloff': float(props.shrink_falloff),
        'shrink_shift': [float(v) for v in props.shrink_shift],
        'face_full_transform': bool(props.face_full_transform),
        'eye_sink': float(props.eye_sink),
        'eye_sink_pad': float(props.eye_sink_pad),
        'eye_region_min': [float(v) for v in props.eye_region_min],
        'eye_region_max': [float(v) for v in props.eye_region_max],
    }


def apply_char_config(props, config):
    """Copy supported keys from a config dict onto props; returns count applied.

    Keys the props do not have (e.g. 'units') are skipped, so a config with
    unit roles can be applied without touching them.
    """
    applied = 0
    for key, value in config.items():
        if key == 'units' or not hasattr(props, key):
            continue
        setattr(props, key, tuple(float(v) for v in value)
                if isinstance(value, (list, tuple)) else value)
        applied += 1
    return applied


def _char_name_update(self, context):
    """Load the saved per-character config when the character name changes.

    No-op when the character has no stored config (fresh character). The
    shrink props' update callbacks fire per key, live-updating HS_Preview.
    """
    if not self.char_name:
        return
    cfg = resolve_char_config(face_offsets_path(), self.char_name.strip())
    if cfg:
        apply_char_config(self, cfg)


def select_import_pairs(pairs, units_map=None):
    """Pick dump pairs for a bulk import: body + face-sized meshes.

    Body = the pair with the most vertices (always included, even if huge);
    face candidates = 50..3000 vertices. Tiny debris and 4MB-class garbage
    buffers are skipped. Returns a sublist in scan order.

    Garbage exclusion: sorted by vert_count descending, any pair that is
    >50000 verts and >=5x the next non-face-sized pair is a 4MB-class
    garbage buffer and is dropped; the scan backs up one position after a
    drop so consecutive garbage buffers are removed too (Noelle dumps
    contain several, and dropping one can expose the previous pair to a new
    5x comparison). Face-sized pairs (50..3000) never act as the comparison
    baseline: a face part cannot be the body, so the body must not be
    dropped merely because it is 5x bigger than a face mesh.

    When units_map is non-empty (per-character {vb0_hash: role} config),
    it is the authoritative character-mesh whitelist: only pairs whose vb0
    is registered are returned, which also drops NPC/effect dumps that the
    heuristic above cannot tell apart. The largest pair is NOT special-cased
    here: a registered dump may contain 4MB-class garbage buffers (e.g.
    Noelle 911ff708) that are not in units, and they must be excluded.
    """
    if units_map:
        return [p for p in pairs if p['vb0'] in units_map]
    if not pairs:
        return []
    by_vert = sorted(pairs, key=lambda p: p['vert_count'], reverse=True)
    i = 0
    while i < len(by_vert) - 1:
        first, second = by_vert[i], by_vert[i + 1]
        if 50 <= second['vert_count'] <= 3000:
            i += 1  # 顔サイズはボディ判定の比較基準にしない
            continue
        if (first['vert_count'] > 50000
                and first['vert_count'] >= 5 * second['vert_count']):
            by_vert.pop(i)  # 4MB クラスゴミ。1 つ戻して再チェック (複数ゴミ対応)
            i = max(0, i - 1)
        else:
            i += 1
    largest = by_vert[0]
    out = []
    for p in pairs:
        if p is largest:
            out.append(p)
        elif 50 <= p['vert_count'] <= 3000:
            out.append(p)
    return out


# ===== PROPERTIES (stored on Scene) =====
_dump_cache = {'pairs': []}  # filled by NHS_OT_AnalyzeDump -> scan_dump_dir()
_last_auto_setup_dir = None  # 直近に auto_setup を実行した dump_dir (連続発火防止)
_last_preview_pair = None  # 直近にプレビューした dump_pair 文字列 (連続発火防止)


def dump_pair_items(self, context):
    """Dynamic EnumProperty items for the analyzed dump pairs."""
    if not _dump_cache['pairs']:
        return [('NONE', 'No dump analyzed', 'Run Analyze Dump first')]
    items = [('NONE', '— Select a pair —', '')]
    for p in _dump_cache['pairs']:
        label = f"{p['vb0'][:8]}/{p['ib'][:8]}  {p['vert_count']}v {p['index_count']}i"
        items.append((f"{p['vb0']}|{p['ib']}", label, f"frame {p['frame']}"))
    return items


def _sync_shrink_box(center, half):
    """Move HS_ShrinkBox to match shrink props (local verts = ±half, origin = center)."""
    obj = bpy.data.objects.get(SHRINK_BOX_NAME)
    if obj is None or obj.type != 'MESH':
        return
    for v, p in enumerate(box_wireframe_verts((0.0, 0.0, 0.0), half)):
        obj.data.vertices[v].co = p
    obj.location = tuple(center)
    obj.data.update()


def _create_shrink_box(coll, center, half):
    """Create (or replace) the HS_ShrinkBox orange wireframe in coll."""
    old = bpy.data.objects.get(SHRINK_BOX_NAME)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    mesh = bpy.data.meshes.new(SHRINK_BOX_NAME)
    mesh.from_pydata(box_wireframe_verts((0.0, 0.0, 0.0), half),
                     box_wireframe_edges(), [])
    mesh.update()
    mat = bpy.data.materials.get('HS_ShrinkBox_Mat')
    if mat is None:
        mat = bpy.data.materials.new('HS_ShrinkBox_Mat')
        mat.diffuse_color = (1.0, 0.55, 0.0, 1.0)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(SHRINK_BOX_NAME, mesh)
    obj.location = tuple(center)
    obj["hs_role"] = "shrink_box"
    coll.objects.link(obj)
    return obj


def _apply_eye_sink(coll, eye_sink, eye_sink_pad, region_min=None,
                    region_max=None):
    """Sink BODY-role verts in the eyes region back along x (display space).

    Region comes from resolve_eye_bboxes(): the user-set eye_region_min/max
    bbox when provided (non-zero), otherwise eye_region_bboxes()'s automatic
    display-space bbox of every EYES-role mesh (location-inclusive).
    BODY-role verts whose display y/z fall inside any bbox +/- pad and
    x <= bmax.x + pad move back by 'eye_sink'. Non-accumulating: it runs
    after preview_shrink_mesh, which recomputes from hs_original_pos, so the
    sink is re-applied to the fresh shrink result every pass (never stacked).
    """
    if eye_sink <= 0.0:
        return
    meshes = [o for o in coll.objects
              if o.type == 'MESH' and o.get('hs_role')]
    boxes = resolve_eye_bboxes(eye_region_bboxes(meshes),
                               region_min, region_max)
    if not boxes:
        return
    for head in [o for o in meshes if o.get('hs_role') == 'BODY']:
        loc = tuple(head.location)
        verts = [(v.co[0] + loc[0], v.co[1] + loc[1], v.co[2] + loc[2])
                 for v in head.data.vertices]
        moved = eye_sink_positions(verts, boxes, eye_sink_pad, eye_sink)
        for v, p in zip(head.data.vertices, moved):
            v.co = (p[0] - loc[0], p[1] - loc[1], p[2] - loc[2])
        head.data.update()


def _preview_props_update(self, context):
    """Live-apply shrink params to HS_Preview meshes (no-op when unavailable).

    Called on every change of shrink_center / shrink_half / shrink_scale.
    Recomputes from hs_original_pos, so it is never accumulative. The shrink
    box wireframe follows center/half (scale/falloff leave its shape unchanged).

    Edit-mode guard: while in EDIT_MESH the bmesh owns the mesh data, so the
    custom attribute hs_original_pos is unreadable via the data API (reads as
    length 0, foreach_get raises TypeError). The property value itself is
    already stored, so the next update after leaving edit mode re-applies it.
    """
    if bpy.context.mode == 'EDIT_MESH':
        return
    coll = bpy.data.collections.get(PREVIEW_COLLECTION)
    if coll is None:
        return
    center = tuple(self.shrink_center)
    half = tuple(self.shrink_half)
    scale = self.shrink_scale
    falloff = self.shrink_falloff
    shift = tuple(self.shrink_shift)
    full = self.face_full_transform
    origin = tuple(self.shrink_origin)
    meshes = [o for o in coll.objects if o.type == 'MESH']
    for obj in meshes:
        preview_shrink_mesh(obj.data, center, half, scale,
                            tuple(obj.location), falloff, shift,
                            full and not is_body_mesh(obj, meshes), origin)
    _apply_eye_sink(coll, self.eye_sink, self.eye_sink_pad,
                    self.eye_region_min, self.eye_region_max)
    _sync_shrink_box(center, half)


def _dump_dir_update(self, context):
    """dump_dir 変更時に自動セットアップを予約 (update コールバック)。

    bpy.ops を update コールバック内から直接呼ぶと再入するため、タイマーで
    0.1 秒後に実行する。同一パスの連続発火は _last_auto_setup_dir で抑止
    (タイマー実行時に更新)。タイマー内 report は不安定なので例外は print。
    units 未登録のキャラでは発火しない (手動ボタンで実行)。
    """
    global _last_auto_setup_dir
    new_dir = bpy.path.abspath(self.dump_dir)
    if not os.path.isdir(new_dir):
        return
    if not _has_registered_units(context.scene.headshrink_props.char_name):
        return  # units 未登録なら自動発火しない (手動ボタンで実行)
    if new_dir == _last_auto_setup_dir:
        return

    def _run_auto_setup():
        global _last_auto_setup_dir
        try:
            _last_auto_setup_dir = new_dir  # 実行時に更新 (再発火防止)
            bpy.ops.headshrink.auto_setup()
        except Exception as exc:  # タイマー内 report は不安定 → print で報告
            print(f"[HeadShrink] auto_setup failed: {exc}")
        return None  # タイマー解除

    bpy.app.timers.register(_run_auto_setup, first_interval=0.1)


def _dump_pair_update(self, context):
    """dump_pair 変更時に選択ペアを即プレビュー表示 (update コールバック)。

    bpy.ops を update コールバック内から直接呼ぶと再入するため、タイマーで
    0.1 秒後に実行する。同一ペアの連続発火は _last_preview_pair で抑止
    (タイマー実行時に更新)。タイマー内 report は不安定なので例外は print。
    """
    global _last_preview_pair
    if not self.dump_pair or self.dump_pair == 'NONE':
        return
    if self.dump_pair == _last_preview_pair:
        return
    pair = self.dump_pair  # クロージャ用に値を保持 (選択が変わる可能性)

    def _run_preview_pair():
        global _last_preview_pair
        try:
            _last_preview_pair = pair  # 実行時に更新 (再発火防止)
            bpy.ops.headshrink.preview_pair()
        except Exception as exc:  # タイマー内 report は不安定 → print で報告
            print(f"[HeadShrink] preview_pair failed: {exc}")
        return None  # タイマー解除

    bpy.app.timers.register(_run_preview_pair, first_interval=0.1)


def _dump_pairs_index_update(self, context):
    """dump_pairs リストの選択変更で選択ペアを即プレビュー表示 (update コールバック)。

    クリック / 上下キーによる選択変更ごとに発火。_last_preview_pair で同一
    ペアの連続発火を抑止し、タイマー 0.1 秒後に preview_pair を実行する
    (update 内から直接 bpy.ops を呼ぶと再入するため)。
    """
    global _last_preview_pair
    try:
        item = self.dump_pairs[self.dump_pairs_index]
    except IndexError:  # リスト空 or index 範囲外
        return
    pair = f"{item.vb0}|{item.ib}"
    if not item.vb0 or pair == _last_preview_pair:
        return

    def _run_preview_pair():
        global _last_preview_pair
        try:
            _last_preview_pair = pair  # 実行時に更新 (再発火防止)
            bpy.ops.headshrink.preview_pair()
        except Exception as exc:  # タイマー内 report は不安定 → print で報告
            print(f"[HeadShrink] preview_pair failed: {exc}")
        return None  # タイマー解除

    bpy.app.timers.register(_run_preview_pair, first_interval=0.1)


class NHSUnitItem(bpy.types.PropertyGroup):
    """units リストの 1 要素 (vb0 ハッシュ + role)。"""

    vb0: bpy.props.StringProperty(name="VB0 Hash", default="")
    role: bpy.props.StringProperty(name="Role", default="OTHER")


class NHSDumpPairItem(bpy.types.PropertyGroup):
    """ダンプ解析結果の 1 ペア (選択 UIList 用)。"""

    pair_name: bpy.props.StringProperty(name="Pair", default="")
    vb0: bpy.props.StringProperty(name="VB0", default="")
    ib: bpy.props.StringProperty(name="IB", default="")
    vert_count: bpy.props.IntProperty(name="Verts", default=0)


class HS_UL_UnitsList(bpy.types.UIList):
    """units リストの表示 (vb0 ハッシュ + role を左右に並べる)。"""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row()
            row.label(text=item.vb0)
            row.label(text=item.role)


class HS_UL_DumpPairList(bpy.types.UIList):
    """解析済みダンプペアの表示 (ペア名 + 頂点数)。

    units 登録済みの vb0 は行頭にチェックアイコン付きで通常表示、未登録は
    BLANK1 + 行全体を薄く表示して区別する。
    """

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            registered = any(u.vb0 == item.vb0
                             for u in context.scene.headshrink_props.units_list)
            row_icon = 'CHECKBOX_HLT' if registered else 'BLANK1'
            if not registered:
                layout.active = False  # 未登録ペアは行全体を薄く表示
            row = layout.row()
            row.label(text=item.pair_name, icon=row_icon)
            row.label(text=f"{item.vert_count}v")


class NHSProps(bpy.types.PropertyGroup):  # bpy.types in Blender 5.x (was bpy.props)
    output_dir: bpy.props.StringProperty(
        name="Output Dir",
        default=r"G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink\assets\Preview",
        subtype='DIR_PATH',
    )
    # ---- 3DMigoto dump workflow ----
    dump_dir: bpy.props.StringProperty(
        name="Dump Dir",
        description="3DMigoto frame dump directory (vb0/ib .buf files)",
        default=r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\assets\Dump\Noelle",
        subtype='DIR_PATH',
        update=_dump_dir_update,
    )
    dump_pair: bpy.props.EnumProperty(
        name="Dump Pair", items=dump_pair_items, default=0,
        update=_dump_pair_update,
    )
    # 常時表示のペア一覧 (UIList 選択用)。解析結果を同期する
    dump_pairs: bpy.props.CollectionProperty(type=NHSDumpPairItem)
    dump_pairs_index: bpy.props.IntProperty(
        name="Dump Pairs Index", default=0,
        update=_dump_pairs_index_update,
    )
    char_name: bpy.props.StringProperty(
        name="Character", default="Noelle",
        description="Character name used for the exported mod and the "
                    "per-character settings store. Changing it loads that "
                    "character's saved shrink parameters",
        update=_char_name_update,
    )
    role_edit: bpy.props.EnumProperty(
        name="Unit Role",
        description="Role assigned to the selected mesh (stored per-character "
                    "via Save Char Config). BODY = body, EYES/MOUTH/BROW = "
                    "face parts, OTHER = untouched",
        items=[
            ('BODY', 'BODY', 'Main body mesh'),
            ('EYES', 'EYES', 'Eyes mesh (pupil pull applies)'),
            ('MOUTH', 'MOUTH', 'Mouth mesh'),
            ('BROW', 'BROW', 'Brow / eyebrow mesh'),
            ('OTHER', 'OTHER', 'Ignored by the mod'),
        ],
        default='BODY',
    )
    # ---- Units (キャラメッシュ登録): ハッシュ直接入力 UI ----
    units_vb0: bpy.props.StringProperty(
        name="VB0 Hash",
        description="3DMigoto ハンティングモードで取得した VB ハッシュ (8桁 hex)",
        default="",
    )
    units_role: bpy.props.EnumProperty(
        name="Unit Role",
        description="このハッシュに割り当てる role (BODY = 本体, "
                    "EYES/MOUTH/BROW = 顔パーツ, OTHER = 対象外)",
        items=[
            ('BODY', 'BODY', 'Main body mesh'),
            ('EYES', 'EYES', 'Eyes mesh (pupil pull applies)'),
            ('MOUTH', 'MOUTH', 'Mouth mesh'),
            ('BROW', 'BROW', 'Brow / eyebrow mesh'),
            ('OTHER', 'OTHER', 'Ignored by the mod'),
        ],
        default='BODY',
    )
    units_list: bpy.props.CollectionProperty(type=NHSUnitItem)
    units_list_index: bpy.props.IntProperty(
        name="Units List Index", default=0,
    )
    # ---- Whole-body preview (CopyDispatch diff) ----
    # Coordinates are display-space (z = up; Genshin x+ = down is rotated away
    # on import). The three params below live-update the HS_Preview meshes.
    shrink_center: bpy.props.FloatVectorProperty(
        name="Shrink Center",
        description="Center of the shrink box in display coords (z = up, y = right, x = forward)",
        size=3, default=(-0.3, 0.0, 0.0), subtype='XYZ',
        update=_preview_props_update,
    )
    shrink_origin: bpy.props.FloatVectorProperty(
        name="Shrink Origin",
        description="Scale pivot of the shrink in display coords (z = up). "
                    "Put it at the neck / rotation center: the head shrinks "
                    "toward this point instead of the box center. Independent "
                    "of Shrink Center: moving the box does not change the "
                    "pivot, so face meshes do not follow the box",
        size=3, default=(0.0, 0.0, 0.5), subtype='TRANSLATION',
        update=_preview_props_update,
    )
    shrink_half: bpy.props.FloatVectorProperty(
        name="Shrink Box Half-Size",
        description="Half-extents of the shrink box along x/y/z (display coords, z = up)",
        size=3, default=(0.5, 0.25, 0.35), subtype='XYZ',
        update=_preview_props_update,
    )
    shrink_scale: bpy.props.FloatProperty(
        name="Shrink Scale",
        description="Vertices inside the box are scaled about Shrink Center by this factor (live)",
        default=0.95, min=0.1, max=1.0, step=0.01, precision=3,
        update=_preview_props_update,
    )
    shrink_falloff: bpy.props.FloatProperty(
        name="Shrink Falloff",
        description="Fade band width beyond the box (ratio of box size). The "
                    "shrink factor blends smoothly back to 1.0 across the "
                    "band. 0.3-0.5 shows the smoothest transition",
        default=0.15, min=0.0, max=1.0, step=0.01, precision=3,
        update=_preview_props_update,
    )
    shrink_shift: bpy.props.FloatVectorProperty(
        name="Shrink Shift",
        description="Translation added to in-box vertices (on top of the "
                    "scale). Use e.g. to push neck vertices down so the "
                    "shrunken head does not leave a gap. Fades to 0 at the "
                    "box boundary like the falloff band",
        size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
        update=_preview_props_update,
    )
    face_full_transform: bpy.props.BoolProperty(
        name="Face Full Transform",
        description="Face meshes (eyes/mouth/brow, everything except the "
                    "main body) ignore the shrink box and transform "
                    "uniformly as a whole (same center/scale/shift). Keeps "
                    "parts aligned and seam-free",
        default=True,
        update=_preview_props_update,
    )
    eye_sink: bpy.props.FloatProperty(
        name="Eye Sink",
        description="Push the head mesh's eye region (the y/z footprint of "
                    "the eyes mesh, or the user-set eye region from 'Use "
                    "Selection as Eye Region') back along x (display coords) "
                    "by this amount. Counteracts the pupil poking out in "
                    "front of the eyelids during blinking / expression "
                    "morphs, which the static CopyDispatch diff cannot "
                    "follow. 0 disables",
        default=0.0, min=0.0, max=0.05, step=0.001, precision=4,
        unit='LENGTH', update=_preview_props_update,
    )
    eye_sink_pad: bpy.props.FloatProperty(
        name="Eye Sink Padding",
        description="Extra margin around the eyes mesh bbox (y/z, and x "
                    "front limit) used to select the head vertices that Eye "
                    "Sink moves. Larger = a wider, smoother sink region",
        default=0.01, min=0.0, max=0.05, step=0.001, precision=4,
        unit='LENGTH', update=_preview_props_update,
    )
    eye_region_min: bpy.props.FloatVectorProperty(
        name="Eye Region Min",
        description="User-set eye region bbox minimum (display coords). "
                    "Overrides the automatic EYES-mesh detection for Eye "
                    "Sink. (0,0,0) = unset, use automatic detection. Set via "
                    "'Use Selection as Eye Region' in Edit mode",
        size=3, subtype='TRANSLATION', default=(0.0, 0.0, 0.0),
        update=_preview_props_update,
    )
    eye_region_max: bpy.props.FloatVectorProperty(
        name="Eye Region Max",
        description="User-set eye region bbox maximum (display coords). "
                    "Overrides the automatic EYES-mesh detection for Eye "
                    "Sink. (0,0,0) = unset, use automatic detection. Set via "
                    "'Use Selection as Eye Region' in Edit mode",
        size=3, subtype='TRANSLATION', default=(0.0, 0.0, 0.0),
        update=_preview_props_update,
    )


# ===== OPERATORS =====
class NHS_OT_AnalyzeDump(bpy.types.Operator):
    bl_idname = "headshrink.analyze_dump"
    bl_label = "Analyze Dump"
    bl_description = "Scan dump dir for (vb0, ib) pairs and cache them"

    def execute(self, context):
        props = context.scene.headshrink_props
        dump_dir = bpy.path.abspath(props.dump_dir)
        if not os.path.isdir(dump_dir):
            self.report({'ERROR'}, f"Dump dir not found: {dump_dir}")
            return {'CANCELLED'}
        pairs = scan_dump_dir(dump_dir)
        _dump_cache['pairs'] = pairs
        # 選択 UIList 用に同期 (解析前にクリアして全ペアを追加)
        props.dump_pairs.clear()
        for p in pairs:
            item = props.dump_pairs.add()
            item.pair_name = f"{p['vb0'][:8]} | {p['ib'][:8]}"
            item.vb0 = p['vb0']
            item.ib = p['ib']
            item.vert_count = p['vert_count']
        if not pairs:
            self.report({'WARNING'}, f"No vb0/ib pairs found in {dump_dir}")
            return {'FINISHED'}
        props.dump_pair = 'NONE'
        self.report({'INFO'}, f"Found {len(pairs)} vb0/ib pairs "
                              f"(e.g. {pairs[0]['vb0'][:8]}/{pairs[0]['ib'][:8]} "
                              f"{pairs[0]['vert_count']}v)")
        return {'FINISHED'}


_HEX8_RE = re.compile(r'^[0-9a-f]{8}$')


class NHS_OT_UnitsAdd(bpy.types.Operator):
    bl_idname = "headshrink.units_add"
    bl_label = "Units Add"
    bl_description = "Register a vb0 hash with a role in the units list"

    def execute(self, context):
        props = context.scene.headshrink_props
        vb0 = props.units_vb0.strip().lower()
        if not _HEX8_RE.match(vb0):
            self.report({'ERROR'}, f"Invalid VB hash: '{props.units_vb0}' "
                                   f"(expected 8 hex digits)")
            return {'CANCELLED'}
        for i, item in enumerate(props.units_list):
            if item.vb0 == vb0:  # 既存 vb0 は role 更新
                item.role = props.units_role
                props.units_list_index = i
                props.units_vb0 = ""
                self.report({'INFO'}, f"Units: {vb0} role -> {props.units_role}")
                return {'FINISHED'}
        item = props.units_list.add()
        item.vb0 = vb0
        item.role = props.units_role
        props.units_list_index = len(props.units_list) - 1
        props.units_vb0 = ""
        self.report({'INFO'}, f"Units: {vb0} registered as {props.units_role}. "
                              f"保存して ③ セットアップで表示")
        return {'FINISHED'}


class NHS_OT_UnitsAddPair(bpy.types.Operator):
    bl_idname = "headshrink.units_add_pair"
    bl_label = "Units Add Pair"
    bl_description = "Register the selected dump pair's vb0 hash in the units list"

    def execute(self, context):
        props = context.scene.headshrink_props
        # 選択 UIList の index からペアを特定
        if (not props.dump_pairs or props.dump_pairs_index < 0
                or props.dump_pairs_index >= len(props.dump_pairs)):
            self.report({'ERROR'}, "Run Analyze Dump and select a pair first")
            return {'CANCELLED'}
        sel = props.dump_pairs[props.dump_pairs_index]
        if not sel.vb0:
            self.report({'ERROR'}, "Selected pair not found. Run Analyze Dump again")
            return {'CANCELLED'}
        vb0 = sel.vb0
        for i, item in enumerate(props.units_list):
            if item.vb0 == vb0:  # 既存 vb0 は role 更新
                item.role = props.units_role
                props.units_list_index = i
                self.report({'INFO'}, f"Units: {vb0} role -> {props.units_role}")
                return {'FINISHED'}
        item = props.units_list.add()
        item.vb0 = vb0
        item.role = props.units_role
        props.units_list_index = len(props.units_list) - 1
        self.report({'INFO'}, f"Units: {vb0} registered as {props.units_role}. "
                              f"保存して ③ セットアップで表示")
        return {'FINISHED'}


class NHS_OT_UnitsRemove(bpy.types.Operator):
    bl_idname = "headshrink.units_remove"
    bl_label = "Units Remove"
    bl_description = "Remove the selected units entry"

    def execute(self, context):
        props = context.scene.headshrink_props
        if props.units_list_index < 0 or props.units_list_index >= len(props.units_list):
            self.report({'WARNING'}, "No units entry selected")
            return {'CANCELLED'}
        props.units_list.remove(props.units_list_index)
        if props.units_list_index >= len(props.units_list):
            props.units_list_index = len(props.units_list) - 1
        self.report({'INFO'}, "Units: entry removed")
        return {'FINISHED'}


class NHS_OT_UnitsSave(bpy.types.Operator):
    bl_idname = "headshrink.units_save"
    bl_label = "Units Save"
    bl_description = "Save the units list into face_offsets.json for the current character"

    def execute(self, context):
        props = context.scene.headshrink_props
        char_name = props.char_name.strip()
        if not char_name:
            self.report({'ERROR'}, "Character name is empty")
            return {'CANCELLED'}
        path = face_offsets_path()
        cfg = load_char_config(path, char_name)
        cfg['units'] = {item.vb0: item.role for item in props.units_list}
        save_char_config(path, char_name, {}, cfg)
        self.report({'INFO'}, f"Units saved for {char_name}: "
                              f"{len(props.units_list)} entries。③ セットアップで表示")
        return {'FINISHED'}


class NHS_OT_UnitsLoad(bpy.types.Operator):
    bl_idname = "headshrink.units_load"
    bl_label = "Units Load"
    bl_description = "Load the saved units of the current character into the list"

    def execute(self, context):
        props = context.scene.headshrink_props
        char_name = props.char_name.strip()
        units = load_char_config(face_offsets_path(), char_name).get('units', {})
        props.units_list.clear()
        for vb0, role in units.items():
            item = props.units_list.add()
            item.vb0 = str(vb0)
            item.role = str(role)
        props.units_list_index = 0
        self.report({'INFO'}, f"Units loaded: {len(props.units_list)} entries "
                              f"for {char_name}。③ セットアップを押すとモデル表示")
        return {'FINISHED'}


def _import_pair(context, pair, units_map=None):
    """Import one dump pair into HeadShrink_Dump with role assignment.

    Replaces any existing Dump_<vb0> object. Adds hs_original_pos + the
    hs_vb0_hash/hs_ib_hash/hs_vert_count/hs_role custom properties. Role comes
    from the per-character units map first, else largest pair = BODY, else
    OTHER. Returns (obj, role, nverts, ntris, max_index); raises OSError/
    ValueError on load failure.
    """
    if units_map is None:
        units_map = {}
    verts, faces, max_index = load_dump_mesh(pair['vb0_path'], pair['ib_path'])
    coll = bpy.data.collections.get(DUMP_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(DUMP_COLLECTION)
        context.scene.collection.children.link(coll)
    name = f"Dump_{pair['vb0']}"
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    # Original display-coordinate positions for preview shrink/reset
    attr = mesh.attributes.new(name='hs_original_pos',
                               type='FLOAT_VECTOR', domain='POINT')
    attr.data.foreach_set('vector', [c for p in verts for c in p])
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    obj["hs_vb0_hash"] = pair['vb0']
    obj["hs_ib_hash"] = pair['ib']
    obj["hs_vert_count"] = pair['vert_count']
    # ゴミ除外後の選択候補基準で最大判定 (ゴミが最大でも真のボディが BODY になる)
    candidates = select_import_pairs(_dump_cache['pairs'], units_map)
    is_largest = all(pair['vert_count'] >= p['vert_count']
                     for p in candidates)
    role = role_for_pair(pair['vb0'], pair['vert_count'], units_map, is_largest)
    obj["hs_role"] = role
    return obj, role, len(verts), len(faces), max_index


class NHS_OT_ImportDump(bpy.types.Operator):
    bl_idname = "headshrink.import_dump"
    bl_label = "Import Dump Pair"
    bl_description = "Import selected dump pair as a mesh into HeadShrink_Dump"

    def execute(self, context):
        props = context.scene.headshrink_props
        pair = next((p for p in _dump_cache['pairs']
                     if f"{p['vb0']}|{p['ib']}" == props.dump_pair), None)
        if pair is None:
            self.report({'ERROR'}, "Run Analyze Dump and select a pair first")
            return {'CANCELLED'}
        units_map = load_char_config(
            face_offsets_path(), props.char_name.strip()).get('units', {})
        try:
            obj, role, nv, nf, mi = _import_pair(context, pair, units_map)
        except (OSError, ValueError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Imported {obj.name}: {nv} verts, "
                              f"{nf} tris (role {role}, max index {mi})")
        return {'FINISHED'}


class NHS_OT_ImportAll(bpy.types.Operator):
    bl_idname = "headshrink.import_all"
    bl_label = "Import All"
    bl_description = "Auto-import the body (largest pair) + face-sized pairs (50..3000 verts)"

    def execute(self, context):
        props = context.scene.headshrink_props
        units_map = load_char_config(
            face_offsets_path(), props.char_name.strip()).get('units', {})
        pairs = select_import_pairs(_dump_cache['pairs'], units_map)
        if not pairs:
            self.report({'ERROR'}, "Run Analyze Dump first (no candidate pairs)")
            return {'CANCELLED'}
        imported = 0
        failed = 0
        for pair in pairs:
            try:
                _import_pair(context, pair, units_map)
                imported += 1
            except (OSError, ValueError):
                failed += 1
        self.report({'INFO'}, f"Imported {imported} mesh(es) into "
                              f"{DUMP_COLLECTION} (skipped {failed} failed)")
        return {'FINISHED'}


def _clear_scene():
    """シーン内の全オブジェクトと専用コレクションを削除する。削除数を返す。

    HeadShrink_Dump / HS_Preview は後で再作成されるので中身ごと削除。
    リストをコピーしてから回す (イテレーション中の削除を避ける)。
    """
    removed = 0
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
        removed += 1
    for coll_name in (DUMP_COLLECTION, PREVIEW_COLLECTION):
        coll = bpy.data.collections.get(coll_name)
        if coll is not None:
            bpy.data.collections.remove(coll)
    return removed


class NHS_OT_AutoSetup(bpy.types.Operator):
    bl_idname = "headshrink.auto_setup"
    bl_label = "Auto Setup (1-Click)"
    bl_description = "Clear the scene, import body + face pairs and set up the preview in one click"

    def execute(self, context):
        props = context.scene.headshrink_props
        dump_dir = bpy.path.abspath(props.dump_dir)
        if not os.path.isdir(dump_dir):
            self.report({'ERROR'}, f"Dump dir not found: {dump_dir}")
            return {'CANCELLED'}
        # シーン内の全オブジェクトと専用コレクションを削除
        removed = _clear_scene()
        # ダンプを再スキャンして選択ペアをインポート
        _dump_cache['pairs'] = scan_dump_dir(dump_dir)
        if not _dump_cache['pairs']:
            self.report({'WARNING'}, f"No vb0/ib pairs found in {dump_dir}")
            return {'FINISHED'}
        units_map = load_char_config(
            face_offsets_path(), props.char_name.strip()).get('units', {})
        pairs = select_import_pairs(_dump_cache['pairs'], units_map)
        imported = 0
        failed = 0
        for pair in pairs:
            try:
                _import_pair(context, pair, units_map)
                imported += 1
            except (OSError, ValueError):
                failed += 1
        # Preview Setup 相当 (共通実装)
        result = _preview_setup_impl(self, context)
        if result != {'FINISHED'}:
            return result
        self.report({'INFO'}, f"Auto setup: {removed} object(s) cleared, "
                              f"{imported} mesh(es) imported ({failed} failed), "
                              f"preview ready")
        return {'FINISHED'}


def _preview_setup_impl(self, context):
    """Shared Preview Setup body (NHS_OT_PreviewSetup / NHS_OT_AutoSetup).

    Duplicates the dump meshes into HS_Preview, auto-places shared face
    units onto the body's head, re-applies saved face offsets, switches the
    3D viewport to SOLID and draws the shrink box. self must expose
    report(); returns an operator status dict.
    """
    src = bpy.data.collections.get(DUMP_COLLECTION)
    if src is None:
        self.report({'ERROR'}, f"No {DUMP_COLLECTION} collection (Import Dump first)")
        return {'CANCELLED'}
    src_objs = [o for o in src.objects
                if o.type == 'MESH' and o.get('hs_vb0_hash')]
    if not src_objs:
        self.report({'ERROR'}, f"No hs_vb0_hash meshes in {DUMP_COLLECTION}")
        return {'CANCELLED'}
    # Re-apply the saved per-character config (shrink params + units) so a
    # Preview Setup always restores the last saved state for this char.
    props = context.scene.headshrink_props
    cfg = load_char_config(face_offsets_path(), props.char_name.strip())
    if cfg:
        apply_char_config(props, cfg)
    # Recreate HS_Preview
    old = bpy.data.collections.get(PREVIEW_COLLECTION)
    if old is not None:
        for o in list(old.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(old)
    coll = bpy.data.collections.new(PREVIEW_COLLECTION)
    context.scene.collection.children.link(coll)
    for s in src_objs:
        mesh = s.data.copy()
        obj = bpy.data.objects.new(s.name, mesh)
        obj.location = s.location
        obj.rotation_euler = s.rotation_euler
        obj.scale = s.scale
        obj["hs_vb0_hash"] = s["hs_vb0_hash"]
        obj["hs_role"] = s.get('hs_role', 'OTHER')
        coll.objects.link(obj)
    # Auto-place shared face units onto the body's head: the face VBs are
    # character-shared and dumped in their own local space, so they appear
    # near the waist. Offset each by (head_center - face_center) on the
    # object location (display coords; user can still tweak with G).
    preview_objs = [o for o in coll.objects if o.type == 'MESH']
    if preview_objs:
        main = max(preview_objs, key=lambda o: len(o.data.vertices))
        head_center = head_center_from_verts(
            [tuple(v.co) for v in main.data.vertices])
        if head_center is not None:
            for o in preview_objs:
                if o is main:
                    continue
                verts = [tuple(v.co) for v in o.data.vertices]
                if not verts:
                    continue
                face_center = tuple(
                    sum(p[i] for p in verts) / len(verts) for i in range(3))
                o.location = tuple(head_center[i] - face_center[i]
                                   for i in range(3))
        # Re-apply saved per-character face offsets if any (overrides auto
        # placement with the user's G-key tweaks from a previous session).
        saved = load_face_offsets(face_offsets_path(),
                                  context.scene.headshrink_props.char_name)
        for o in preview_objs:
            if o.name in saved:
                o.location = tuple(saved[o.name])
        # Record the final placement (after auto-placement + saved offsets)
        # so Reset Preview can restore G-key moved faces to the setup-time
        # position. Stored per-vertex (POINT domain) like hs_original_pos;
        # read back via data[0].vector.
        for o in preview_objs:
            loc = tuple(o.location)
            attr = o.data.attributes.new(
                name='hs_original_loc', type='FLOAT_VECTOR', domain='POINT')
            attr.data.foreach_set('vector', list(loc) * len(o.data.vertices))
    # Solid display in any 3D viewport
    if context.screen:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'SOLID'
    # Hide the source dump collection: originals keep their dumped local
    # positions (shared face VBs sit near the waist) and would confuse the
    # preview if left visible next to the auto-placed copies.
    src.hide_viewport = True
    # Orange wireframe of the shrink box, origin at shrink_center so the
    # user can grab it with G and Apply Box Position reads it back.
    props = context.scene.headshrink_props
    _create_shrink_box(coll, tuple(props.shrink_center),
                       tuple(props.shrink_half))
    self.report({'INFO'}, f"Preview ready: {len(src_objs)} meshes in {PREVIEW_COLLECTION}")
    return {'FINISHED'}


class NHS_OT_PreviewSetup(bpy.types.Operator):
    bl_idname = "headshrink.preview_setup"
    bl_label = "Setup Preview"
    bl_description = "Duplicate dump meshes into HS_Preview collection for whole-body editing"

    def execute(self, context):
        return _preview_setup_impl(self, context)


class NHS_OT_PreviewPair(bpy.types.Operator):
    bl_idname = "headshrink.preview_pair"
    bl_label = "Preview Selected Pair"
    bl_description = "Clear the scene, import the selected dump pair and set up the preview"

    def execute(self, context):
        props = context.scene.headshrink_props
        # 選択 UIList の index からペアを特定
        if (not props.dump_pairs or props.dump_pairs_index < 0
                or props.dump_pairs_index >= len(props.dump_pairs)):
            self.report({'ERROR'}, "Run Analyze Dump and select a pair first")
            return {'CANCELLED'}
        sel = props.dump_pairs[props.dump_pairs_index]
        if not sel.vb0:
            self.report({'ERROR'}, "Selected pair not found in the dump cache "
                                   "(run Analyze Dump again)")
            return {'CANCELLED'}
        pair = next((p for p in _dump_cache['pairs']
                     if p['vb0'] == sel.vb0 and p['ib'] == sel.ib), None)
        if pair is None:
            self.report({'ERROR'}, "Selected pair not found in the dump cache "
                                   "(run Analyze Dump again)")
            return {'CANCELLED'}
        # シーン内の全オブジェクトと専用コレクションを削除
        _clear_scene()
        units_map = load_char_config(
            face_offsets_path(), props.char_name.strip()).get('units', {})
        try:
            obj, role, nv, nf, mi = _import_pair(context, pair, units_map)
        except (OSError, ValueError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        result = _preview_setup_impl(self, context)
        if result != {'FINISHED'}:
            return result
        self.report({'INFO'}, f"Preview: {pair['vb0'][:8]} "
                              f"({pair['vert_count']}v, role {role})")
        return {'FINISHED'}


class NHS_OT_PreviewApply(bpy.types.Operator):
    bl_idname = "headshrink.preview_apply"
    bl_label = "Apply Preview Shrink"
    bl_description = "Recompute in-box shrink from original positions (non-accumulating)"

    def execute(self, context):
        if bpy.context.mode == 'EDIT_MESH':
            self.report({'ERROR'},
                        "Edit モード中は適用できません。Edit モードを終了してから実行してください")
            return {'CANCELLED'}
        props = context.scene.headshrink_props
        coll = bpy.data.collections.get(PREVIEW_COLLECTION)
        if coll is None:
            self.report({'ERROR'}, f"No {PREVIEW_COLLECTION} collection (Preview Setup first)")
            return {'CANCELLED'}
        center = tuple(props.shrink_center)
        half = tuple(props.shrink_half)
        scale = props.shrink_scale
        falloff = props.shrink_falloff
        shift = tuple(props.shrink_shift)
        full = props.face_full_transform
        origin = tuple(props.shrink_origin)
        meshes = [o for o in coll.objects if o.type == 'MESH']
        count = 0
        for obj in meshes:
            if preview_shrink_mesh(obj.data, center, half, scale,
                                   tuple(obj.location), falloff, shift,
                                   full and not is_body_mesh(obj, meshes),
                                   origin):
                count += 1
        _apply_eye_sink(coll, props.eye_sink, props.eye_sink_pad,
                        props.eye_region_min, props.eye_region_max)
        self.report({'INFO'}, f"Preview shrink applied to {count} mesh(es) "
                              f"(scale={scale:.3f})")
        return {'FINISHED'}


class NHS_OT_SetEyeRegion(bpy.types.Operator):
    bl_idname = "headshrink.set_eye_region"
    bl_label = "Use Selection as Eye Region"
    bl_description = "Set the Eye Sink region from the selected BODY-mesh " \
                     "vertices (Edit mode)"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.get('hs_role') == 'BODY'
                and context.mode == 'EDIT_MESH')

    def execute(self, context):
        obj = context.active_object
        if (obj is None or obj.type != 'MESH'
                or obj.get('hs_role') != 'BODY'
                or context.mode != 'EDIT_MESH'):
            self.report({'ERROR'},
                        "Select eye-region vertices in EDIT mode on the BODY mesh")
            return {'CANCELLED'}
        import bmesh
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        sel = [v.index for v in bm.verts if v.select]
        if not sel:
            self.report({'ERROR'},
                        "No vertices selected: select the eye region on the "
                        "BODY mesh in Edit mode")
            return {'CANCELLED'}
        bbox = selection_display_bbox(obj.data, sel, obj.location)
        if bbox is None:
            self.report({'ERROR'}, "Empty eye region bbox")
            return {'CANCELLED'}
        # Leave edit mode before assigning props: the update callback
        # (_preview_props_update) reads hs_original_pos via the data API,
        # which bmesh owns while in EDIT_MESH (reads as length 0). Assigning
        # in OBJECT mode makes the preview re-apply safely, then edit mode is
        # restored (vertex selection is kept in the mesh data).
        props = context.scene.headshrink_props
        prev_mode = bpy.context.mode
        if prev_mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='OBJECT')
        props.eye_region_min = bbox[0]
        props.eye_region_max = bbox[1]
        if prev_mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, f"Eye region set from {len(sel)} vertices: "
                              f"{tuple(round(v, 4) for v in bbox[0])} .. "
                              f"{tuple(round(v, 4) for v in bbox[1])}")
        return {'FINISHED'}


class NHS_OT_ClearEyeRegion(bpy.types.Operator):
    bl_idname = "headshrink.clear_eye_region"
    bl_label = "Clear Eye Region"
    bl_description = "Reset the Eye Sink region to automatic EYES-mesh detection"

    def execute(self, context):
        props = context.scene.headshrink_props
        # Same edit-mode detour as NHS_OT_SetEyeRegion: props assignment
        # triggers _preview_props_update, which needs the data API.
        prev_mode = bpy.context.mode
        if prev_mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='OBJECT')
        props.eye_region_min = (0.0, 0.0, 0.0)
        props.eye_region_max = (0.0, 0.0, 0.0)
        if prev_mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'},
                    "Eye region cleared: automatic detection restored")
        return {'FINISHED'}


class NHS_OT_PreviewReset(bpy.types.Operator):
    bl_idname = "headshrink.preview_reset"
    bl_label = "Reset Preview"
    bl_description = "Restore vertices from the saved hs_original_pos attribute"

    def execute(self, context):
        coll = bpy.data.collections.get(PREVIEW_COLLECTION)
        if coll is None:
            self.report({'ERROR'}, f"No {PREVIEW_COLLECTION} collection")
            return {'CANCELLED'}
        count = 0
        for obj in coll.objects:
            if obj.type != 'MESH':
                continue
            mesh = obj.data
            attr = mesh.attributes.get('hs_original_pos')
            if attr is None:
                continue
            flat = [0.0] * (len(mesh.vertices) * 3)
            attr.data.foreach_get('vector', flat)
            for v in range(len(mesh.vertices)):
                mesh.vertices[v].co = flat[v * 3:(v + 1) * 3]
            mesh.update()
            # 顔メッシュの配置位置もセットアップ直後に戻す (G キー移動の復元)
            loc_attr = mesh.attributes.get('hs_original_loc')
            if loc_attr is not None:
                obj.location = tuple(loc_attr.data[0].vector)
            count += 1
        self.report({'INFO'},
                    f"Preview reset (verts + location) on {count} mesh(es)")
        return {'FINISHED'}


class NHS_OT_SaveFaceOffsets(bpy.types.Operator):
    bl_idname = "headshrink.save_face_offsets"
    bl_label = "Save Char Config"
    bl_description = "Save HS_Preview mesh locations + all shrink params for the current character (re-applied on Preview Setup / char switch)"

    def execute(self, context):
        props = context.scene.headshrink_props
        coll = bpy.data.collections.get(PREVIEW_COLLECTION)
        if coll is None or not any(o.type == 'MESH' for o in coll.objects):
            self.report({'ERROR'}, f"No meshes in {PREVIEW_COLLECTION} "
                                   f"(Preview Setup first)")
            return {'CANCELLED'}
        char_name = props.char_name.strip() or 'Char'
        locations = {o.name: [round(v, 6) for v in o.location]
                     for o in coll.objects if o.type == 'MESH'}
        units = {o['hs_vb0_hash']: o.get('hs_role', 'OTHER')
                 for o in coll.objects
                 if o.type == 'MESH' and o.get('hs_vb0_hash')}
        config = extract_char_config(props)
        config['units'] = units
        path = face_offsets_path()
        n = save_char_config(path, char_name, locations, config)
        self.report({'INFO'}, f"Saved char config for {char_name} "
                              f"({n} mesh(es), {len(config)} settings) -> {path}")
        return {'FINISHED'}


class NHS_OT_SaveDefaultConfig(bpy.types.Operator):
    bl_idname = "headshrink.save_default_config"
    bl_label = "Save Default"
    bl_description = "Save current shrink params as the shared default for all characters (applied to characters without their own config)"

    def execute(self, context):
        props = context.scene.headshrink_props
        config = extract_char_config(props)
        path = face_offsets_path()
        save_char_config(path, DEFAULT_CONFIG_KEY, {}, config)
        self.report({'INFO'}, f"Default config saved "
                              f"({len(config)} settings) -> {path}")
        return {'FINISHED'}


class NHS_OT_LoadCharConfig(bpy.types.Operator):
    bl_idname = "headshrink.load_char_config"
    bl_label = "Load Char Config"
    bl_description = "Apply the saved char config (shrink params) for the current character"

    def execute(self, context):
        props = context.scene.headshrink_props
        char_name = props.char_name.strip() or 'Char'
        cfg = load_char_config(face_offsets_path(), char_name)
        applied = apply_char_config(props, cfg)
        if applied == 0:
            self.report({'INFO'}, f"No saved config for {char_name}")
        else:
            self.report({'INFO'}, f"Loaded {applied} settings for {char_name}")
        return {'FINISHED'}


class NHS_OT_LoadDefaultConfig(bpy.types.Operator):
    bl_idname = "headshrink.load_default_config"
    bl_label = "Load Default"
    bl_description = "Apply the shared default config (__default__) to the current props"

    def execute(self, context):
        props = context.scene.headshrink_props
        cfg = load_char_config(face_offsets_path(), DEFAULT_CONFIG_KEY)
        applied = apply_char_config(props, cfg)
        if applied == 0:
            self.report({'INFO'}, "No default config saved")
        else:
            self.report({'INFO'}, f"Loaded {applied} default settings")
        return {'FINISHED'}


class NHS_OT_ExportDiff(bpy.types.Operator):
    bl_idname = "headshrink.export_diff"
    bl_label = "Mod Export"
    bl_description = "Write <char><Unit>Base/Key.buf + <char>Head.hlsl + <char>.ini (CopyDispatch)"

    def execute(self, context):
        props = context.scene.headshrink_props
        char_name = props.char_name.strip() or 'Char'
        output_dir = os.path.join(bpy.path.abspath(props.output_dir), char_name)
        coll = bpy.data.collections.get(PREVIEW_COLLECTION)
        if coll is None:
            self.report({'ERROR'}, f"No {PREVIEW_COLLECTION} collection (Preview Setup first)")
            return {'CANCELLED'}
        os.makedirs(output_dir, exist_ok=True)
        meshes = [o for o in coll.objects
                  if o.type == 'MESH' and o.get('hs_vb0_hash')]
        units = []
        for obj in meshes:
            vb0 = obj['hs_vb0_hash']
            mesh = obj.data
            attr = mesh.attributes.get('hs_original_pos')
            if attr is None:
                self.report({'ERROR'}, f"{obj.name}: no hs_original_pos (run Preview Apply first)")
                return {'CANCELLED'}
            vert_count = len(mesh.vertices)
            flat = [0.0] * (vert_count * 3)
            attr.data.foreach_get('vector', flat)
            # Base = original (pre-shrink) positions, back to game space so the
            # .buf files match the dump. The HLSL delta shader reads only the
            # position component, so normal/tangent are left zero.
            base_verts = [display_to_game(tuple(flat[i:i + 3]))
                          for i in range(0, len(flat), 3)]
            base_data = replace_positions(bytes(vert_count * DUMP_STRIDE), base_verts, DUMP_STRIDE)
            unit = unit_name_for_role(obj.get('hs_role', 'OTHER'), vb0)
            name = char_name + unit
            # v.co already carries every preview transform (shrink, shift)
            # because preview_shrink_mesh writes back local coords. Export
            # the mesh state as-is; the delta shader pushes it toward the
            # head every frame. The body (box mode) is never shifted.
            verts = [display_to_game(tuple(v.co)) for v in mesh.vertices]
            key_data = replace_positions(base_data, verts, DUMP_STRIDE)
            with open(os.path.join(output_dir, f"{name}Base.buf"), 'wb') as f:
                f.write(base_data)
            with open(os.path.join(output_dir, f"{name}Key.buf"), 'wb') as f:
                f.write(key_data)
            units.append({'name': name, 'vb_hash': vb0, 'vert_count': vert_count})
        if not units:
            self.report({'ERROR'}, "No hs_vb0_hash meshes in HS_Preview")
            return {'CANCELLED'}
        with open(os.path.join(output_dir, f"{char_name}Head.hlsl"), 'w', newline='\n') as f:
            f.write(DIFF_HLSL)
        with open(os.path.join(output_dir, f"{char_name}.ini"), 'w', newline='\n') as f:
            f.write(build_diff_ini(char_name, units))
        self.report({'INFO'}, f"Diff mod exported to {output_dir} "
                              f"({len(units)} unit(s): "
                              f"{', '.join(u['name'] for u in units)})")
        return {'FINISHED'}


class NHS_OT_SetRole(bpy.types.Operator):
    bl_idname = "headshrink.set_role"
    bl_label = "Set Role"
    bl_description = "Assign the selected role to the active dump mesh (saved via Save Char Config)"

    def execute(self, context):
        props = context.scene.headshrink_props
        obj = context.active_object
        if obj is None or obj.type != 'MESH' or not obj.get('hs_vb0_hash'):
            self.report({'ERROR'},
                        "Select a HeadShrink_Dump / HS_Preview mesh first")
            return {'CANCELLED'}
        obj['hs_role'] = props.role_edit
        self.report({'INFO'}, f"{obj.name}: role -> {props.role_edit}")
        return {'FINISHED'}


class NHS_OT_ApplyBoxPosition(bpy.types.Operator):
    bl_idname = "headshrink.apply_box_position"
    bl_label = "Apply Box Position"
    bl_description = "Read the moved HS_ShrinkBox position into Shrink Center"

    def execute(self, context):
        props = context.scene.headshrink_props
        obj = bpy.data.objects.get(SHRINK_BOX_NAME)
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, f"No {SHRINK_BOX_NAME} (Preview Setup first)")
            return {'CANCELLED'}
        center = box_center_from_obj(obj)
        if center is None:
            self.report({'ERROR'}, f"{SHRINK_BOX_NAME} has no vertices")
            return {'CANCELLED'}
        for i in range(3):
            props.shrink_center[i] = center[i]  # update fires -> re-shrink + box sync
        self.report({'INFO'}, f"Shrink Center = "
                              f"({center[0]:.4f}, {center[1]:.4f}, {center[2]:.4f})")
        return {'FINISHED'}


class NHS_OT_CenterOnHead(bpy.types.Operator):
    bl_idname = "headshrink.center_on_head"
    bl_label = "Center = Head"
    bl_description = "Snap Shrink Center to the main body mesh's head center"

    def execute(self, context):
        props = context.scene.headshrink_props
        coll = bpy.data.collections.get(PREVIEW_COLLECTION)
        if coll is None:
            self.report({'ERROR'}, f"No {PREVIEW_COLLECTION} (Preview Setup first)")
            return {'CANCELLED'}
        meshes = [o for o in coll.objects if o.type == 'MESH']
        if not meshes:
            self.report({'ERROR'}, f"No meshes in {PREVIEW_COLLECTION}")
            return {'CANCELLED'}
        main = max(meshes, key=lambda o: len(o.data.vertices))
        center = head_center_from_verts([tuple(v.co) for v in main.data.vertices])
        if center is None:
            self.report({'ERROR'}, "Could not compute head center")
            return {'CANCELLED'}
        for i in range(3):
            props.shrink_center[i] = center[i]
        self.report({'INFO'}, f"Shrink Center = head "
                              f"({center[0]:.4f}, {center[1]:.4f}, {center[2]:.4f})")
        return {'FINISHED'}


class NHS_PT_Panel(bpy.types.Panel):
    bl_label = "HeadShrink"
    bl_idname = "NHS_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HeadShrink"

    def draw(self, context):
        layout = self.layout
        props = context.scene.headshrink_props

        layout.label(text="① ディレクトリ → ② 登録 → ③ セットアップ → ④ 調整 → ⑤ 生成",
                     icon='INFO')

        # ---- Step 1: ダンプディレクトリ ----
        layout.separator()
        box = layout.box()
        box.label(text="① ダンプディレクトリ", icon='FILE_FOLDER')
        box.prop(props, "dump_dir")
        box.label(text="② で解析、③ でセットアップ。units 登録済みなら"
                       "変更時に自動セットアップ", icon='INFO')

        # ---- Step 2: キャラメッシュ登録 (Units) ----
        box = layout.box()
        box.label(text="② キャラメッシュ登録 (Units)", icon='GROUP')
        box.prop(props, "char_name")
        box.operator("headshrink.analyze_dump", icon='FILE_REFRESH')
        box.label(text="ダンプを解析して候補ペアを表示", icon='INFO')
        box.template_list("HS_UL_DumpPairList", "dump_pairs", props,
                          "dump_pairs", props, "dump_pairs_index", rows=6)
        box.label(text="選択 (クリック/上下キー) で自動プレビュー表示。確認しながら登録",
                  icon='INFO')
        box.operator("headshrink.preview_pair", icon='RESTRICT_VIEW_OFF',
                     text="選択ペアを表示")
        row = box.row()
        row.prop(props, "units_role", text="")
        row.operator("headshrink.units_add_pair", icon='ADD',
                     text="表示中のペアを登録")
        box.label(text="または VB ハッシュを直接入力:", icon='INFO')
        row = box.row(align=True)
        row.prop(props, "units_vb0", text="VB")
        row.prop(props, "units_role", text="")
        box.operator("headshrink.units_add", icon='ADD')
        box.template_list("HS_UL_UnitsList", "units_list", props,
                          "units_list", props, "units_list_index", rows=3)
        row = box.row()
        row.operator("headshrink.units_remove", icon='X')
        row.operator("headshrink.units_load", icon='FILE_REFRESH')
        row.operator("headshrink.units_save", icon='FILE_TICK')
        box.label(text="登録したら【保存】→ ③ セットアップで表示。"
                       "フィールドのみならボディ 1 つで OK。"
                       "UI 画面も縮めるなら目/口/眉も登録",
                  icon='INFO')

        # ---- Step 3: セットアップ ----
        box = layout.box()
        box.label(text="③ セットアップ", icon='PLAY')
        box.operator("headshrink.auto_setup", icon='PLAY')
        box.label(text="既存オブジェクトを全削除し、② で登録したモデルを読込 → "
                       "プレビュー配置まで実行", icon='INFO')
        box.label(text="units 未登録の状態で押すと最大ペアのみ読込。"
                       "ダンプ解析結果からペアを選んで登録してから実行が基本",
                  icon='INFO')

        # ---- Step 4: 頭部調整 (プレビュー) ----
        box = layout.box()
        box.label(text="④ 頭部調整 (プレビュー)", icon='VIEWZOOM')
        box.label(text="Display coords: Z=up, Y=right, X=forward", icon='INFO')
        box.label(text="顔メッシュは本体頭部に自動配置。G キーで微調整可", icon='INFO')
        box.operator("headshrink.preview_reset", icon='LOOP_BACK')
        row = box.row()
        row.operator("headshrink.save_face_offsets", icon='FILE_TICK')
        row.operator("headshrink.load_char_config", icon='FILE_REFRESH')
        row = box.row()
        row.operator("headshrink.save_default_config", icon='FILE_TICK')
        row.operator("headshrink.load_default_config", icon='FILE_REFRESH')
        box.label(text="顔メッシュ位置はキャラごとに保存・自動適用される",
                  icon='INFO')
        box.label(text="Save Default: 現在の値を全キャラ共通の基準として保存。"
                       "Load Default: 基準値を現在の設定に適用", icon='INFO')
        box.prop(props, "shrink_center")
        box.prop(props, "shrink_origin")
        box.label(text="縮小中心 (首元等の回転中心)。Box 位置とは独立",
                  icon='INFO')
        box.prop(props, "shrink_half")
        box.prop(props, "shrink_scale")
        box.prop(props, "shrink_falloff")
        box.prop(props, "shrink_shift")
        box.prop(props, "eye_sink")
        box.prop(props, "eye_sink_pad")
        row = box.row()
        row.operator("headshrink.set_eye_region", icon='RESTRICT_SELECT_OFF')
        row.operator("headshrink.clear_eye_region", icon='X')
        box.label(text="瞳領域: 自動判定 (EYES メッシュ位置基準)。Edit モードで瞳の頂点を選択 → "
                       "Use Selection で上書き。Clear で自動判定に戻る",
                  icon='INFO')
        box.label(text="Eye Sink: Body メッシュの目領域のみ (自動判定 or 選択指定) を"
                       "後ろに凹ませ、モーフ中の黒目浮きを相殺",
                  icon='INFO')
        box.prop(props, "face_full_transform")
        row = box.row()
        row.operator("headshrink.center_on_head", icon='TRACKER')
        row.operator("headshrink.apply_box_position", icon='CHECKMARK')
        box.label(text="Box はワイヤーフレームで表示。G キーで移動 → "
                       "Apply Box Position で反映", icon='INFO')

        # ---- Step 5: mod 生成 (出力) ----
        box = layout.box()
        box.label(text="⑤ mod 生成 (出力)", icon='EXPORT')
        box.prop(props, "output_dir")
        box.operator("headshrink.export_diff", icon='EXPORT')


# ===== REGISTRATION =====
classes = (
    NHSUnitItem,
    NHSDumpPairItem,
    HS_UL_UnitsList,
    HS_UL_DumpPairList,
    NHSProps,
    NHS_OT_AnalyzeDump,
    NHS_OT_UnitsAdd,
    NHS_OT_UnitsAddPair,
    NHS_OT_UnitsRemove,
    NHS_OT_UnitsSave,
    NHS_OT_UnitsLoad,
    NHS_OT_ImportDump,
    NHS_OT_ImportAll,
    NHS_OT_AutoSetup,
    NHS_OT_PreviewPair,
    NHS_OT_PreviewSetup,
    NHS_OT_PreviewApply,
    NHS_OT_PreviewReset,
    NHS_OT_SaveFaceOffsets,
    NHS_OT_SaveDefaultConfig,
    NHS_OT_LoadCharConfig,
    NHS_OT_LoadDefaultConfig,
    NHS_OT_ExportDiff,
    NHS_OT_SetRole,
    NHS_OT_ApplyBoxPosition,
    NHS_OT_CenterOnHead,
    NHS_OT_SetEyeRegion,
    NHS_OT_ClearEyeRegion,
    NHS_PT_Panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.headshrink_props = bpy.props.PointerProperty(type=NHSProps)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.headshrink_props


if __name__ == "__main__":
    register()
