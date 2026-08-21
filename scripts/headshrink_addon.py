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
    "version": (2, 0, 1),
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
import glob

try:
    import bpy
except ImportError:  # headless import (unit tests / py_compile)
    bpy = None  # type: ignore[assignment]
try:
    import numpy as np  # Blender 同梱 (境界マッチングで使用)
except ImportError:
    np = None  # type: ignore[assignment]

# ===== CONSTANTS =====
DUMP_STRIDE = 40                    # Genshin standard position stride (float3 at offset 0)
DUMP_INDEX_BYTES = 2                # 16-bit IB only (R16_UINT)
DUMP_COLLECTION = "HeadShrink_Dump"
DEFAULT_POSITION_VS = "653c63ba4a73ca8b"  # skinning (pointlist) pass VS hash



# ===== DUMP PIPELINE (bpy-independent) =====
_DUMP_FRAME_RE = re.compile(r'^(\d+)-vb0=([0-9a-fA-F]+)')
_DUMP_IB_RE = re.compile(r'^(\d+)-ib=([0-9a-fA-F]+)')
_PS_T0_FRAME_RE = re.compile(r'^(\d+)-ps-t0=([0-9a-fA-F]+)')


def _scan_vb_ps_t0_map(dump_dir):
    """vb0 -> ps-t0 diffuse hash マップを FrameAnalysis ファイル名から収集。

    規則: 000005-vb0=<hash>-vs=<vs>-ps=<ps>.buf と同フレーム
    000005-ps-t0=<texHash>-vs=<vs>-ps=<ps>.dds が同一フレーム番号+同一 vs/ps
    でペアリングされる場合、vb0 の描画時 ps-t0 テクスチャ hash を得られる。
    deduped フォルダは ps-t0 無しなので無視。vs/ps 無しのファイルはスキップ。
    """
    vb_entries: dict = {}
    ps_entries: dict = {}
    vs_re = re.compile(r'-vs=([0-9a-f]{8})')
    ps_re = re.compile(r'-ps=([0-9a-f]{8})')
    try:
        walk = list(os.walk(dump_dir))
    except OSError:
        return {}
    for root, _dirs, files in walk:
        if os.path.basename(root) == 'deduped':
            continue
        rel = os.path.relpath(root, dump_dir)
        prefix = '' if rel == '.' else rel + os.sep
        for fn in files:
            low = fn.lower()
            if low.endswith('.buf') and 'vb0=' in low:
                m = _DUMP_FRAME_RE.match(fn)
                if not m:
                    continue
                vs_m = vs_re.search(low)
                ps_m = ps_re.search(low)
                if not (vs_m and ps_m):
                    continue
                key = prefix + m.group(1) + f"-vs={vs_m.group(1)}-ps={ps_m.group(1)}"
                vb_entries[key] = m.group(2).lower()[:8]
            elif low.endswith('.dds') and 'ps-t0=' in low:
                m = _PS_T0_FRAME_RE.match(fn)
                if not m:
                    continue
                vs_m = vs_re.search(low)
                ps_m = ps_re.search(low)
                if not (vs_m and ps_m):
                    continue
                key = prefix + m.group(1) + f"-vs={vs_m.group(1)}-ps={ps_m.group(1)}"
                tex = m.group(2).lower()
                if len(tex) > 8:
                    tex = tex[:8]
                ps_entries[key] = tex
    out: dict = {}
    for k, vb_h in vb_entries.items():
        tex = ps_entries.get(k)
        if tex and vb_h not in out:
            out[vb_h] = tex
    return out


def _scan_drawn_vb0(dump_dir):
    """Draw-visible vb0 hashes (exclude SO-only like bbdaf598)."""
    drawn = set()
    try:
        walk = list(os.walk(dump_dir))
    except OSError:
        return drawn
    log_paths = [os.path.join(r, f) for r, _, fs in walk for f in fs if f.lower() == 'log.txt']
    hr = re.compile(r'hash=([0-9a-fA-F]{8})')
    tr = re.compile(r'IASetPrimitiveTopology\(Topology:(\d+)')
    for lp in log_paths:
        try:
            lines = open(lp, encoding='utf-8', errors='ignore').readlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            if 'DrawIndexed(' not in line and not re.search(r'\bDraw\(VertexCount', line):
                continue
            # topology check: skip pointlist skinning
            topo = None
            for k in range(i, max(-1, i-40), -1):
                m = tr.search(lines[k])
                if m:
                    topo = m.group(1)
                    break
            if topo == '1':
                continue
            for k in range(i-1, max(-1, i-40), -1):
                if 'IASetVertexBuffers' in lines[k]:
                    for hm in hr.finditer(lines[k]):
                        drawn.add(hm.group(1).lower()[:8])
                    for t in range(k+1, i):
                        if 'resource=' in lines[t] or 'view=' in lines[t]:
                            for hm in hr.finditer(lines[t]):
                                drawn.add(hm.group(1).lower()[:8])
                    break
    return drawn


def _scan_ib_splits(dump_dir):
    """Parse log.txt DrawIndexed -> {ib_hash: [(first_index, index_count)...]}.

    Scans each FrameAnalysis*/log.txt under dump_dir. IASetIndexBuffer hash
    -> subsequent DrawIndexed(IndexCount, StartIndexLocation) is recorded.
    deduped per hash. Returns {} when no log.txt found.
    """
    splits: dict = {}
    try:
        walk = list(os.walk(dump_dir))
    except OSError:
        return {}
    log_paths = []
    for root, _dirs, files in walk:
        for fn in files:
            if fn.lower() == 'log.txt':
                log_paths.append(os.path.join(root, fn))
    ib_re = re.compile(r'IASetIndexBuffer.*hash=([0-9a-f]{8})', re.IGNORECASE)
    draw_re = re.compile(r'DrawIndexed\(IndexCount:(\d+),\s*StartIndexLocation:(\d+)')
    for lp in log_paths:
        try:
            with open(lp, encoding='utf-8', errors='ignore') as f:
                cur_ib = None
                for line in f:
                    m = ib_re.search(line)
                    if m:
                        cur_ib = m.group(1).lower()
                    m2 = draw_re.search(line)
                    if m2 and cur_ib:
                        cnt = int(m2.group(1))
                        first = int(m2.group(2))
                        splits.setdefault(cur_ib, set()).add((first, cnt))
                        cur_ib = None
        except OSError:
            continue
    return {k: sorted(v) for k, v in splits.items()}


def _find_ib_path(dump_dir, ib_hash):
    """Find any .buf file whose name contains ib=<hash>."""
    h = ib_hash.lower()[:8]
    try:
        for root, _dirs, files in os.walk(dump_dir):
            for fn in files:
                if f'ib={h}' in fn.lower():
                    return os.path.join(root, fn)
    except OSError:
        pass
    return ''


def _has_ib_split(ib_splits):
    """True when log.txt shows same IB drawn with >=2 first_index values."""
    return any(len(v) >= 2 for v in (ib_splits or {}).values())


def _resolve_drawn_vb_hash(dump_cache, vb_hash, vert_count):
    """Return drawn vb0 hash with same vert_count when vb_hash is SO-only.

    Generic: when vb_hash not in drawn_vb0 (e.g. bbdaf598 SO-only) but a
    drawn vb0 with identical vert_count exists (e.g. e36be83b), return the
    drawn one. Uses dump_cache['drawn_vb0'] and scans dump_dir for size match.
    No hard-coded hash.
    """
    drawn = (dump_cache or {}).get('drawn_vb0') or set()
    if not drawn:
        return vb_hash
    if vb_hash and vb_hash.lower()[:8] in drawn:
        return vb_hash
    position_vb = (dump_cache or {}).get('position_vb') or {}
    # Try position_vb entries that are drawn and match vert_count
    for h, info in position_vb.items():
        if h.lower()[:8] in drawn and info.get('vert_count') == vert_count:
            return h
    # Fallback: scan dump_dir via cache-bypass (scan for drawn .buf with same size)
    # Caller already has scan_dir logic for body_hash; keep minimal here and let
    # caller handle filesystem scan if needed. Return original when no match.
    return vb_hash


def _find_paired_ibs(dump_dir, vb_hash):
    """Find IB hashes that share same frame+vs+ps with vb_hash (Body pairing).

    Generic: scans dump_dir filenames for vb0=vb_hash and ib=* sharing the
    same prefix (frame) and same vs/ps hashes. Returns set of paired ib hashes.
    Used to limit IB split output to the Body's IB only (e.g. ec1ed3c9).
    """
    if not dump_dir or not os.path.isdir(dump_dir):
        return set()
    target = vb_hash.lower()[:8]
    # Map (frame_key, vs, ps) -> {vb_hashes}, {ib_hashes}
    vb_groups = {}
    ib_groups = {}
    vs_re = re.compile(r'-vs=([0-9a-f]{8})')
    ps_re = re.compile(r'-ps=([0-9a-f]{8})')
    for root, _dirs, files in os.walk(dump_dir):
        if os.path.basename(root) == 'deduped':
            continue
        rel = os.path.relpath(root, dump_dir)
        prefix = '' if rel == '.' else rel + os.sep
        for fn in files:
            low = fn.lower()
            if not low.endswith('.buf'):
                continue
            m_vb = _DUMP_FRAME_RE.match(fn)
            m_ib = _DUMP_IB_RE.match(fn)
            if m_vb:
                vs_m = vs_re.search(low)
                ps_m = ps_re.search(low)
                if not (vs_m and ps_m):
                    continue
                key = prefix + m_vb.group(1) + f"-vs={vs_m.group(1)}-ps={ps_m.group(1)}"
                vb_groups.setdefault(key, set()).add(m_vb.group(2).lower()[:8])
            elif m_ib:
                vs_m = vs_re.search(low)
                ps_m = ps_re.search(low)
                if not (vs_m and ps_m):
                    continue
                key = prefix + m_ib.group(1) + f"-vs={vs_m.group(1)}-ps={ps_m.group(1)}"
                ib_groups.setdefault(key, set()).add(m_ib.group(2).lower()[:8])
    paired = set()
    for key, vb_set in vb_groups.items():
        if target in vb_set:
            ibs = ib_groups.get(key)
            if ibs:
                paired.update(ibs)
    return paired


def _find_largest_vb0(all_files):
    """Largest vb0 .buf among all_files by vert_count (fake Body candidate)."""
    best = None
    best_vc = -1
    for root, fn in all_files:
        low = fn.lower()
        if not low.endswith('.buf'):
            continue
        is_deduped = os.path.basename(root) == 'deduped'
        m = re.search(r'vb0=([0-9a-f]{8})', low)
        if m:
            h = m.group(1).lower()
        elif is_deduped and re.fullmatch(r'[0-9a-f]{8}', os.path.splitext(fn)[0].lower()):
            h = os.path.splitext(fn)[0].lower()
        else:
            continue
        p = os.path.join(root, fn)
        try:
            vc = os.path.getsize(p) // DUMP_STRIDE
        except OSError:
            continue
        if vc > best_vc:
            best_vc = vc
            best = {'vb_hash': h, 'path': p, 'vert_count': vc}
    return best


def _find_real_position_vb(position_vb):
    """Largest position_vb with 500..100k verts (real Body for IB-split)."""
    cands = [(h, info) for h, info in (position_vb or {}).items()
             if 500 < info.get('vert_count', 0) < 100000]
    if not cands:
        return None
    h, info = max(cands, key=lambda x: x[1]['vert_count'])
    return {'vb_hash': h, 'path': info['path'], 'vert_count': info['vert_count'], 'vs': info.get('vs', '')}


def _is_fake_body_pair(pair, dump_cache):
    """IB-split + vert mismatch => preview is fake Body."""
    ib_splits = dump_cache.get('ib_splits') or {}
    if not _has_ib_split(ib_splits):
        return False
    pos = dump_cache.get('position_vb') or {}
    if not pos:
        return False
    pos_verts = {info.get('vert_count') for info in pos.values()}
    if pair.get('vert_count') not in pos_verts and any(500 < v < 100000 for v in pos_verts):
        return True
    return False


def scan_dump_dir(dump_dir, position_vs=DEFAULT_POSITION_VS):
    """Scan a 3DMigoto frame dump dir -> list of (vb0, ib) pairs.

    Pairs files 'NNNNNN-vb0=<hash>-...' with 'NNNNNN-ib=<hash>-...' sharing the
    same frame number. vert_count/index_count are derived from file sizes
    (stride 40 / 16-bit). Same (vb0, ib) hash pair seen in several frames is
    deduped (identical content).

    Subdirectories are scanned recursively (the user may point dump_dir at a
    parent folder containing multiple FrameAnalysis-* dirs). by_frame keys use
    the subdir-relative path + frame number to avoid collisions across dirs.

    Also records pre-skin position buffers: vb0 files whose name contains
    '-vs=<position_vs>-' (the skinning pass VS) into the global
    _dump_cache['position_vb'] = {vb_hash: {'path', 'vert_count', 'vs'}}.
    These non-indexed buffers have the same vertex count/order as the draw
    vb0, so positions can be transplanted for anim-following vb replacement.
    """
    try:
        walk = list(os.walk(dump_dir))
    except OSError:
        return []
    by_frame = {}
    all_files = []  # (root, fn) — position_vb 検出用 (全サブディレクトリ)
    for root, _dirs, files in walk:
        rel = os.path.relpath(root, dump_dir)
        prefix = '' if rel == '.' else rel + os.sep
        for fn in files:
            all_files.append((root, fn))
            m = _DUMP_FRAME_RE.match(fn)
            if m:
                # サブディレクトリ相対パス + フレーム番号でキー化
                # (FrameAnalysis ごとに 000001 から始まるため衝突防止)
                key = prefix + m.group(1)
                by_frame.setdefault(key, {})['vb0'] = (
                    m.group(2).lower(), os.path.join(root, fn))
                continue
            m = _DUMP_IB_RE.match(fn)
            if m:
                key = prefix + m.group(1)
                by_frame.setdefault(key, {})['ib'] = (
                    m.group(2).lower(), os.path.join(root, fn))
    # Pre-skin position buffers (skinning pass, no IB -> not in pairs).
    # vb0/ib ペアと独立に全ファイルを走査 (ハッシュ付き position_vb は
    # _DUMP_FRAME_RE にマッチするため、ここで別途拾う必要がある)。
    position_vb = {}
    vs_re = re.compile(rf'-vs={re.escape(position_vs)}(?:-|\.)')
    for root, fn in all_files:
        low = fn.lower()
        # vb0 ファイル (ハッシュ付き -vb0= または ハッシュなし -vb0-) かつ
        # スキニングパスの VS 一致のみ position_vb として記録。
        if not (low.endswith('.buf') and ('vb0=' in low or '-vb0-' in low)
                and vs_re.search(low)):
            continue
        m = re.search(r'vb0=([0-9a-f]{8})', low)
        if m:
            h = m.group(1)
        else:
            # ハッシュなし形式 (000001-vb0-vs=...): position_vs をキーに使う
            h = position_vs
        if h in position_vb:
            continue
        path = os.path.join(root, fn)
        position_vb[h] = {
            'path': path,
            'vert_count': os.path.getsize(path) // DUMP_STRIDE,
            'vs': position_vs,
        }
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
        # vs 抽出 (vb0 ファイル名から -vs=<hash>、無ければ '')
        vs_m = re.search(r'-vs=([0-9a-f]{8})',
                         os.path.basename(vb0_path).lower())
        out.append({
            'vb0': vb0_hash, 'ib': ib_hash, 'frame': frame,
            'vert_count': os.path.getsize(vb0_path) // DUMP_STRIDE,
            'index_count': os.path.getsize(ib_path) // DUMP_INDEX_BYTES,
            'vb0_path': vb0_path, 'ib_path': ib_path,
            'vs': vs_m.group(1) if vs_m else '',
        })
    # Draw-filter for position_vb: exclude SO-only hashes (e.g. bbdaf598)
    try:
        drawn_vb0 = _scan_drawn_vb0(dump_dir)
    except Exception:
        drawn_vb0 = set()
    _dump_cache['drawn_vb0'] = drawn_vb0
    # フィルタ前の pre-skin セットを保存 (IB分割キャラの Position 置換用。
    # drawn filter は BodyGate 用に残す)
    _dump_cache['pre_skin_vb'] = position_vb
    if drawn_vb0:
        # keep only drawn hashes; fallback to original when filter empties (log incomplete)
        filtered = {h: info for h, info in position_vb.items() if h.lower()[:8] in drawn_vb0}
        if filtered:
            position_vb = filtered
    _dump_cache['position_vb'] = position_vb
    try:
        ib_splits = _scan_ib_splits(dump_dir)
    except Exception:
        ib_splits = {}
    _dump_cache['ib_splits'] = ib_splits
    # Fallback: IB が match_first_index で Head/Body/Dress に分割されるケース
    # (例: 1066a76c: [0,41385,85527]) は position_vb と draw vb0 が同フレームで
    # ペアにならず out が空に見える。プレビューは偽Body (最大 vb0, vert_count
    # が合わなくても) を is_fake_body で x,y=0 に置くだけ、Export は正規
    # position_vb (例 28247) で BodyPosition.buf を吐く汎用分岐。ハードコード
    # hash は使わず log.txt の DrawIndexed パース (ib_splits) で任意の IB 分割
    # を検出する。
    if ib_splits and _has_ib_split(ib_splits):
        # 最も分割数の多い / 最大総indexの IB を Body 候補として選ぶ
        best_ib = None
        best_splits = None
        best_total = -1
        for ib_hash, splits in ib_splits.items():
            if len(splits) < 2:
                continue
            total = sum(c for _, c in splits)
            if total > best_total:
                best_total = total
                best_ib = ib_hash
                best_splits = splits
        if best_ib and best_splits:
            largest = _find_largest_vb0(all_files)
            real = _find_real_position_vb(position_vb)
            # 偽Bodyプレビュー条件: IB分割あり かつ largest と real の vert_count が不一致
            need_fake = False
            if largest and real and largest['vert_count'] != real['vert_count']:
                need_fake = True
            if need_fake and largest and real:
                if (largest['vb_hash'], best_ib) not in seen:
                    ib_path = _find_ib_path(dump_dir, best_ib)
                    if not ib_path:
                        for p in out:
                            if p['ib'] == best_ib:
                                ib_path = p['ib_path']
                                break
                    if ib_path and os.path.exists(largest['path']):
                        body_first, body_cnt = max(best_splits, key=lambda x: x[1])
                        out.append({
                            'vb0': largest['vb_hash'],
                            'ib': best_ib,
                            'first_index': body_first,
                            'first_count': body_cnt,
                            'ib_splits': best_splits,
                            'is_split': True,
                            'is_fake_body': True,
                            'real_vb_hash': real['vb_hash'],
                            'real_vb_path': real['path'],
                            'real_vert_count': real['vert_count'],
                            'frame': 'synthetic:' + best_ib[:8],
                            'vert_count': largest['vert_count'],
                            'index_count': body_cnt,
                            'vb0_path': largest['path'],
                            'ib_path': ib_path,
                            'vs': real.get('vs', '')[:8] if real.get('vs') else '',
                        })
                        seen.add((largest['vb_hash'], best_ib))
                        _dump_cache['real_position_vb'] = real
            else:
                # フォールバック: 従来の正規 Body 合成 (偽が不要なキャラや largest 未検出時)
                existing_vb0s = {p['vb0'] for p in out}
                cand_list = [(h, info) for h, info in position_vb.items()
                             if h not in existing_vb0s
                             and 500 < info['vert_count'] < 100000]
                if cand_list:
                    cand_hash, cand_info = max(cand_list, key=lambda x: x[1]['vert_count'])
                    if (cand_hash, best_ib) not in seen:
                        ib_path = _find_ib_path(dump_dir, best_ib)
                        if not ib_path:
                            for p in out:
                                if p['ib'] == best_ib:
                                    ib_path = p['ib_path']
                                    break
                        if ib_path:
                            body_first, body_cnt = max(best_splits, key=lambda x: x[1])
                            out.append({
                                'vb0': cand_hash,
                                'ib': best_ib,
                                'first_index': body_first,
                                'first_count': body_cnt,
                                'ib_splits': best_splits,
                                'is_split': True,
                                'frame': 'synthetic:' + best_ib[:8],
                                'vert_count': cand_info['vert_count'],
                                'index_count': body_cnt,
                                'vb0_path': cand_info['path'],
                                'ib_path': ib_path,
                                'vs': cand_info.get('vs', '')[:8] if cand_info.get('vs') else '',
                            })
                            seen.add((cand_hash, best_ib))
    try:
        _dump_cache['vb_ps_t0'] = _scan_vb_ps_t0_map(dump_dir)
    except Exception:
        _dump_cache['vb_ps_t0'] = {}
    return out


def find_secondary_vb0s(pairs, units):
    """セカンダリ VB を検出して {vb0: role} を返す。

    同一 (ib, vs) グループ内に複数の vb0 があり、そのうち units (vb0 -> role)
    に登録済みのものがある場合、units に無い vb0 をセカンダリとして、
    プライマリと同じ role で返す (複数グループ可、dict でマージ)。
    units が空なら {}。
    """
    if not units:
        return {}
    groups = {}
    for p in pairs:
        key = (p['ib'], p.get('vs', ''))
        groups.setdefault(key, set()).add(p['vb0'])
    secondary = {}
    for (_ib, _vs), vb0s in groups.items():
        if len(vb0s) < 2:
            continue
        registered = vb0s & set(units.keys())
        if not registered:
            continue
        role = units[next(iter(registered))]
        for vb0 in vb0s - registered:
            secondary[vb0] = role
    return secondary


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


# position_vb (pre-skin buffer, skinning pass vs=653c63ba4a73ca8b) is in
# y-up MODEL-LOCAL space, unlike draw_vb which is x-down game space. The
# game VS re-skins position_vb every frame; overriding it therefore needs
# the model-local frame, not game space:
#   position_vb -> display: (dx, dy, dz) = (-lx, -lz, +ly)
#   display -> position_vb: (lx, ly, lz) = (-dx, +dz, -dy)
def position_vb_to_display(p):
    """position_vb (y-up model-local) -> display: (-p.x, -p.z, +p.y)."""
    return (-p[0], -p[2], p[1])


def display_to_position_vb(p):
    """display -> position_vb (y-up model-local). Inverse of position_vb_to_display."""
    return (-p[0], p[2], -p[1])


def preview_shrink_mesh(mesh, center, half, scale, offset=(0.0, 0.0, 0.0),
                        falloff=0.0, shift=(0.0, 0.0, 0.0), all_verts=False,
                        origin=None):
    """Recompute vertex coords from hs_original_pos (non-accumulating).

    Shrink-box test and scaling happen in display space (vertex + object
    offset); results are written back in local coordinates. offset=(0,0,0)
    behaves exactly like plain local-space shrinking. all_verts=True skips
    the box test (uniform shrink+shift over the whole mesh). origin is the
    scale pivot in display coords; callers pass the box center so shrinking
    heads toward the box middle. Returns True when applied; False when the
    mesh has no hs_original_pos attribute.
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


def load_dump_mesh(vb0_path, ib_path, stride=DUMP_STRIDE,
                   transform=game_to_display):
    """Read a stride-40 vb0 + 16-bit ib -> (verts, faces, max_index).

    Faces follow IB order (3 indices per triangle). Vertices are returned in
    display coordinates (transform applied; draw vb0 uses game_to_display,
    position_vb uses position_vb_to_display). Raises ValueError on odd
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
    verts = [transform(struct.unpack_from('<3f', vb, i * stride))
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

    origin is the scale pivot: the box test (d vs center/half) picks WHICH
    vertices transform, while scaling happens about 'origin'. origin=None
    keeps the legacy pivot = center; callers typically pass center so the
    head shrinks toward the box middle.

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


def build_position_buf(dump_bytes, game_verts, stride=DUMP_STRIDE):
    """Replace the position float3 of each vertex in a real dump vb0 buffer.

    normal/tangent/etc. bytes are kept from the dump; only bytes 0..12 change.
    game_verts must already be in game space (display_to_game applied by the
    caller). This is the Bennett vb0-replacement path: the game VS re-skins
    these positions every frame, so animations follow exactly.
    """
    out = bytearray(dump_bytes)
    for v, p in enumerate(game_verts):
        struct.pack_into('<3f', out, v * stride, *p)
    return bytes(out)


def find_position_vb(dump_cache, vb_hash, vert_count, drawn_filter=True):
    """Pre-skin position buffer matching a draw vb0 (by vertex count).

    The skinning pass renders non-indexed: its vb0 (position_vb) has the
    same vertex count and vertex order as the draw vb0, so positions can be
    transplanted directly (the game VS re-skins them every frame). Returns
    {'path', 'vert_count', 'vs', 'vb_hash'} for the first position_vb whose
    vert_count matches, else None.

    Drawn filter: when _dump_cache['drawn_vb0'] is non-empty (log.txt present),
    only hashes that were seen before a non-pointlist Draw are considered.
    bbdaf598 (SO-only) is thus excluded in favour of e36be83b. Falls back to
    unfiltered when the filter would eliminate all candidates (log missing or
    incomplete).

    drawn_filter=False: pre-skin (SO-only) hash も対象にする (IB分割キャラの
    Position 置換用。drawn filter は BodyGate 用に残す)。scan_dump_dir が
    保存した _dump_cache['pre_skin_vb'] (フィルタ前) を優先する。
    """
    position_vb = (dump_cache or {}).get('position_vb') or {}
    if not drawn_filter:
        position_vb = (dump_cache or {}).get('pre_skin_vb') or position_vb
    drawn = (dump_cache or {}).get('drawn_vb0')
    if drawn_filter and drawn:
        filtered = {h: info for h, info in position_vb.items() if h.lower()[:8] in drawn}
        # fallback to full set when filter empties (log missing hash)
        if filtered:
            position_vb = filtered
    for h, info in position_vb.items():
        if info.get('vert_count') == vert_count:
            return dict(info, vb_hash=h)
    return None


def _clean_export_dir(output_dir, char_name):
    """Remove stale files from a previous export (same char only).

    Deletes <char>.ini, <char>*.hlsl and <char>*.buf so switching export
    modes (VB Replace vs CopyDispatch) leaves no orphaned Base/Key/Position
    buffers behind. Files whose name does not start with the char name are
    left untouched. Returns the number of files removed.
    """
    removed = 0
    if not os.path.isdir(output_dir):
        return 0
    for pattern in (f"{char_name}.ini",
                    f"{char_name}*.hlsl",
                    f"{char_name}*.buf"):
        for fn in glob.glob(os.path.join(output_dir, pattern)):
            try:
                os.remove(fn)
                removed += 1
            except OSError:
                pass
    return removed


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


# 1フレームだけ別hashに差し替わるキャラ向けの追加hash (role -> [hash8...])。
# 追加hashは同一role/vert_countのdeltaを共有する (元unitのBase/Keyを流用)。
# ハードコード禁止: extra_hashes はキャラconfig (face_offsets.json の
# __config__.extra_hashes) と、Mod Export時の自動検出
# (auto_extra_hashes: 同キャラの複数FrameAnalysisから同サイズ別hashを
# 自動で extra_hash として ini に追加) からのみ供給される。手動で追記する
# 場合は face_offsets.json の該当キャラ __config__ に
#   "extra_hashes": {"MOUTH": ["d265427c"]}
# のように書く (dump_scan.py が同一vert_countの別hash候補を提示する)。


def build_diff_ini(char, units, mode='VB_REPLACE', extra_hashes=None, vb_ps_t0=None, face_diffuse_hash=None, body_hash=None, ib_splits=None):
    """units: [{name(char+Unit), vb_hash, vert_count, role?}] -> ini text.

    VB_REPLACE mode (Bennett-mimic): a unit with role='BODY' gets a plain vb0
    buffer override ([TextureOverride] + [Resource...Position] with the
    pre-skin position buffer) so the game VS keeps animating it — no
    CommandList/CustomShader. Every other unit (face roles, no role) keeps
    the legacy CopyDispatch structure. COPY_DISPATCH mode renders all units
    via CopyDispatch regardless of role.

    extra_hashes: {role: [hash8...]} — 1フレームだけ別hashに差し替わる
    キャラ向け。追加hashは同一role/vert_countのdeltaを共有するため、元unitの
    Base/Key ファイルを流用した TextureOverride/CommandList/CustomShader
    ブロックを追加出力する (Dispatch も元と同じ vert_count)。既に units に
    同名 hash の unit がある場合はスキップ (重複 override 防止)。

    vb_ps_t0: deprecated — 旧 per-draw ps-t0 gating (body_hash/face_diffuse_hashが
    与えられれば無視、effieface式 $is ゲートを優先)。

    body_hash: effieface式 BodyGate hash (BODY position_vb hash, キャラ固有)。
    与えられれば先頭に [TextureOverrideBodyGate] hash=<hash> $is=1 を出し、
    各 face系 TextureOverride は if $is / endif でガード。BODY は VB置換の
    トリガーなのでガード対象外。Noneなら face_diffuse_hash にフォールバック、
    どちらも無ければゲート無し。units内にBODYがあれば自動検出も行う。

    face_diffuse_hash: deprecated fallback (共有皮膚テクスチャのため非推奨)。
    body_hash優先で、body無し時のみ旧 [TextureOverrideFaceDiffuse] として使用。
    """
    # effieface式: $is を global/post で初期化 (BodyGate専用)
    parts = ["[Constants]", "global $is = 0", "", "[Present]", "post $is = 0", ""]
    # body優先、無ければ faceDiffuseフォールバック (body_hashは ExportDiffが units内BODYから供給)
    gate_hash = None
    gate_name = "BodyGate"
    if body_hash:
        gate_hash = str(body_hash).lower()[:8]
        gate_name = "BodyGate"
    elif face_diffuse_hash:
        gate_hash = str(face_diffuse_hash).lower()[:8]
        gate_name = "FaceDiffuse"
    elif vb_ps_t0:
        gate_hash = str(vb_ps_t0).lower()[:8]
        gate_name = "BodyGate"
    if gate_hash:
        parts += [
            f"[TextureOverride{gate_name}]",
            f"hash = {gate_hash}",
            "$is = 1",
            "",
        ]
    existing_hashes = {u['vb_hash'] for u in units}
    for u in units:
        n = u['name']
        if mode == 'VB_REPLACE' and u.get('role') == 'BODY':
            ib_hash = u.get('ib') or u.get('ib_hash')
            splits = u.get('ib_splits')
            has_split = bool(ib_hash and splits and len(splits) >= 2)
            # Lan Yan など IB 分割方式では Position と IB Body が同名で衝突するため
            # Position の TextureOverride 名を charPosition に退避しつつ
            # Resource/ファイルは従来の n (=charBody) のままにして ExportDiff の
            # 書き出し (namePosition.buf) と一致させる
            pos_override = f"{char}Position" if has_split else n
            pos_resource = n
            parts += [
                f"[TextureOverride{pos_override}]",
                # IB分割キャラは pre-skin (SO) hash を置換 (drawn hash だと
                # モデルローカル座標で上書きしてアニメ停止+体消滅する)
                f"hash = {u.get('position_hash') or u['vb_hash']}",
                f"vb0 = Resource{pos_resource}Position",
                "$is = 1",
                "",
                f"[Resource{pos_resource}Position]",
                "type = Buffer",
                f"stride = {DUMP_STRIDE}",
                f"filename = {pos_resource}Position.buf",
                "",
            ]
            # IB match_first_index split (e.g. Lan Yan 1066a76c: Head 0 / Body 41385 / Dress 85527)
            # 補助: u に ib / ib_splits があれば Head/Body/Dress の 3分割を出力
            if has_split:
                # キャッチオール: match_first_index に掛からない Body/Dress の
                # DrawIndexed がスライスIB範囲外を読むのを防ぐ (LanYanMod 実証済み)
                parts += [
                    f"[TextureOverride{char}IB]",
                    f"hash = {ib_hash}",
                    "handling = skip",
                    "drawindexed = auto",
                    "",
                ]
                splits_sorted = sorted(splits)[:3]
                part_names = ['Head', 'Body', 'Dress']
                for idx, (first, cnt) in enumerate(splits_sorted):
                    part = part_names[idx]
                    res_name = f"{char}{part}"
                    # 同一 char で複数 BODY が無い想定、重複は呼び出し側でユニーク化済み
                    parts += [
                        f"[TextureOverride{res_name}]",
                        f"hash = {ib_hash}",
                        f"match_first_index = {first}",
                        f"ib = Resource{res_name}IB",
                        "",
                        f"[Resource{res_name}IB]",
                        "type = Buffer",
                        "format = DXGI_FORMAT_R32_UINT",
                        f"filename = {res_name}.ib",
                        "",
                    ]
            continue
        # effieface式 $is ゲート: BODY は VB置換のトリガーなので対象外、face系のみ if $is
        _use_is = bool(gate_hash and u.get('role') != 'BODY')
        if _use_is:
            parts += [
                f"[TextureOverride{n}]",
                f"hash = {u['vb_hash']}",
                "if $is",
                "$is = 1",
                f"run = CommandList{n}",
                "endif",
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
        else:
            parts += [
                f"[TextureOverride{n}]",
                f"hash = {u['vb_hash']}",
                "$is = 1",
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
        # 追加hash: 元unitの Base/Key を共有 (cs-t0/cs-t1 は元unitの
        # Resource を参照、Dispatch は同一 vert_count)。
        for h in (extra_hashes or {}).get(u.get('role'), []):
            if h in existing_hashes:
                continue
            if _use_is:
                parts += [
                    f"[TextureOverride{n}_{h}]",
                    f"hash = {h}",
                    "if $is",
                    "$is = 1",
                    f"run = CommandList{n}_{h}",
                    "endif",
                    "",
                    f"[CommandList{n}_{h}]",
                    f"Resource{n}_{h}Dif = copy this",
                    f"run = CustomShader{n}_{h}",
                    f"this = Resource{n}_{h}Dif",
                    "",
                    f"[Resource{n}_{h}Dif]",
                    "",
                    f"[CustomShader{n}_{h}]",
                    f"cs = {char}Head.hlsl",
                    "",
                    f"cs-u1 = copy Resource{n}_{h}Dif",
                    f"cs-t0 = copy Resource{n}Base",
                    f"cs-t1 = copy Resource{n}Key",
                    "",
                    f"Dispatch = {u['vert_count']}, 1, 1",
                    f"Resource{n}_{h}Dif = copy cs-u1",
                    "post cs-u1 = null",
                    "",
                ]
            else:
                parts += [
                    f"[TextureOverride{n}_{h}]",
                    f"hash = {h}",
                    "$is = 1",
                    f"run = CommandList{n}_{h}",
                    "",
                    f"[CommandList{n}_{h}]",
                    f"Resource{n}_{h}Dif = copy this",
                    f"run = CustomShader{n}_{h}",
                    f"this = Resource{n}_{h}Dif",
                    "",
                    f"[Resource{n}_{h}Dif]",
                    "",
                    f"[CustomShader{n}_{h}]",
                    f"cs = {char}Head.hlsl",
                    "",
                    f"cs-u1 = copy Resource{n}_{h}Dif",
                    f"cs-t0 = copy Resource{n}Base",
                    f"cs-t1 = copy Resource{n}Key",
                    "",
                     f"Dispatch = {u['vert_count']}, 1, 1",
                    f"Resource{n}_{h}Dif = copy cs-u1",
                    "post cs-u1 = null",
                    "",
                  ]
    if ib_splits:
        done = {str((u.get('ib') or u.get('ib_hash') or '')).lower()[:8] for u in units if u.get('ib_splits')}
        for ib_hash, splits in ib_splits.items():
            key = str(ib_hash).lower()[:8]
            if key in done:
                continue
            norm = []
            for e in splits:
                if isinstance(e, (list, tuple)):
                    norm.append((int(e[0]), int(e[1]) if len(e) > 1 else 0))
                else:
                    norm.append((int(e), 0))
            parts += [
                f"[TextureOverride{char}IB]",
                f"hash = {key}",
                "handling = skip",
                "drawindexed = auto",
                "",
            ]
            for idx, (first, _c) in enumerate(sorted(norm)[:3]):
                part = ['Head', 'Body', 'Dress'][idx]
                res = f"{char}{part}"
                # 重複防止: 同一charで複数IBが来てもセクション名が衝突しないようhashサフィックス
                uniq = f"{res}_{key}"
                parts += [f"[TextureOverride{uniq}]", f"hash = {key}", f"match_first_index = {first}", f"ib = Resource{uniq}IB", "", f"[Resource{uniq}IB]", "type = Buffer", "format = DXGI_FORMAT_R32_UINT", f"filename = {uniq}.ib", ""]
    return "\n".join(parts)


def char_dump_dir(char_name):
    """assets/Dump/<Char> (repo layout: script dir の親) を返す。無ければ None。"""
    try:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'assets', 'Dump')
    except NameError:
        base = os.path.join(os.getcwd(), 'assets', 'Dump')
    d = os.path.join(base, char_name)
    return d if os.path.isdir(d) else None


def auto_extra_hashes(char_name, units, dump_dir=None):
    """Mod Export時に同キャラの複数FrameAnalysisから同サイズ別hashを自動で
    extra_hashとしてiniに追加する。

    assets/Dump/<Char> (無ければ dump_dir フォールバック) 配下の全
    FrameAnalysis-* を再帰走査し、vb0 .buf (raw の vb0=*.buf と
    deduped/*.buf) のファイルサイズから vert_count (=size/40) を導出。
    vsハッシュも併せて記録し、同一 (vert_count, vs) グループ内でのみ
    extraを収集する（vert_countだけ一致の別物まで拾う爆殖を防止）。
    dedupedの vs="" は raw と vs不一致なら除外。vert_count < 10 のノイズ
    (1頂点バッファ等) はスキップ。ダンプが無い環境では {} (エラーにしない)。
    """
    scan_dir = char_dump_dir(char_name) or dump_dir
    if not scan_dir or not os.path.isdir(scan_dir):
        return {}
    groups = {}  # (vert_count, vs) -> set(hash)
    hash_to_vs = {}  # hash -> first vs seen (for unit vs lookup)
    vs_re = re.compile(r'-vs=([0-9a-f]{8})')
    for root, _dirs, files in os.walk(scan_dir):
        for fn in files:
            if not fn.lower().endswith('.buf'):
                continue
            m = _DUMP_FRAME_RE.match(fn)
            if m:
                h = m.group(2).lower()[:8]
            elif os.path.basename(root) == 'deduped':
                h = os.path.splitext(fn)[0].lower()
                if not re.fullmatch(r'[0-9a-f]{8}', h):
                    continue
            else:
                continue
            vc = os.path.getsize(os.path.join(root, fn)) // DUMP_STRIDE
            if vc < 10:
                continue
            vs_m = vs_re.search(fn.lower())
            vs = vs_m.group(1) if vs_m else ''
            groups.setdefault((vc, vs), set()).add(h)
            if h not in hash_to_vs:
                hash_to_vs[h] = vs
    existing = {u['vb_hash'] for u in units}
    out = {}
    for u in units:
        vc = u['vert_count']
        vs = hash_to_vs.get(u['vb_hash'], '')
        # vs一致グループのみを extra 候補に（dedupedの空vsはrawの非空vsと分離）
        candidates = groups.get((vc, vs), set())
        # vs不明(old unit)や deduped由来unitはフォールバックで vc一致全体からも拾う
        # が、空vsグループは除外して爆殖を防ぐ
        if not candidates and vs == '':
            # unit自体がdeduped由来なら vs="" グループを使う
            candidates = groups.get((vc, ''), set())
        extra = sorted(candidates - existing)
        if extra:
            out.setdefault(u.get('role', 'OTHER'), []).extend(extra)
    return out


def _find_face_diffuse_hash(char_name, vb_hashes):
    """assets/Dump/<Char> から FaceDiffuse (ps-t0) を自動検出。

    vb_hashes (face系 vb0 hash集合) の描画時に対応する ps-t0 hashを
    FrameAnalysis ファイル名の同一フレーム+同一 vs/ps ペアリングから収集し、
    最も出現回数が多い ps-t0 を返す。dedupedは除外。見つからなければ None。
    char_dump_dir が無ければ assets/Dump 配下を再帰探索して <Char> を探す
    (★ok サブフォルダ対応)。
    """
    if not vb_hashes:
        return None
    vb_set = {str(h).lower()[:8] for h in vb_hashes}
    dump_dir = char_dump_dir(char_name)
    # ★ok 等のサブフォルダ対応: assets/Dump 配下を再帰探索
    if not dump_dir:
        try:
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'assets', 'Dump')
        except NameError:
            base = os.path.join(os.getcwd(), 'assets', 'Dump')
        if os.path.isdir(base):
            for root, dirs, _files in os.walk(base):
                if os.path.basename(root).lower() == str(char_name).lower():
                    dump_dir = root
                    break
                # 直接の子ディレクトリ名が char_name かもチェック
                for d in dirs:
                    if d.lower() == str(char_name).lower():
                        cand = os.path.join(root, d)
                        if os.path.isdir(cand):
                            dump_dir = cand
                            break
                if dump_dir:
                    break
    if not dump_dir or not os.path.isdir(dump_dir):
        return None
    vs_re = re.compile(r'-vs=([0-9a-f]{8})')
    ps_re = re.compile(r'-ps=([0-9a-f]{8})')
    vb_occurrences = []  # list of (key, vb_hash)
    ps_map: dict = {}
    try:
        walk = list(os.walk(dump_dir))
    except OSError:
        return None
    for root, _dirs, files in walk:
        if os.path.basename(root) == 'deduped':
            continue
        rel = os.path.relpath(root, dump_dir)
        prefix = '' if rel == '.' else rel + os.sep
        for fn in files:
            low = fn.lower()
            if low.endswith('.buf') and 'vb0=' in low:
                m = _DUMP_FRAME_RE.match(fn)
                if not m:
                    continue
                vs_m = vs_re.search(low)
                ps_m = ps_re.search(low)
                if not (vs_m and ps_m):
                    continue
                vb_h = m.group(2).lower()[:8]
                if vb_h not in vb_set:
                    continue
                key = prefix + m.group(1) + f"-vs={vs_m.group(1)}-ps={ps_m.group(1)}"
                vb_occurrences.append((key, vb_h))
            elif low.endswith('.dds') and 'ps-t0=' in low:
                m = _PS_T0_FRAME_RE.match(fn)
                if not m:
                    continue
                vs_m = vs_re.search(low)
                ps_m = ps_re.search(low)
                if not (vs_m and ps_m):
                    continue
                key = prefix + m.group(1) + f"-vs={vs_m.group(1)}-ps={ps_m.group(1)}"
                tex = m.group(2).lower()
                if len(tex) > 8:
                    tex = tex[:8]
                ps_map[key] = tex
    from collections import Counter
    cnt = Counter()
    for k, _vb in vb_occurrences:
        tex = ps_map.get(k)
        if tex:
            cnt[tex] += 1
    if not cnt:
        return None
    return cnt.most_common(1)[0][0]


CONFIG_FILE = 'config.json'
FACE_OFFSETS_FILE = CONFIG_FILE  # backward compat alias
OLD_FACE_OFFSETS_FILE = 'face_offsets.json'
DEFAULT_CONFIG_KEY = '__default__'  # shared per-char fallback config entry
GLOBAL_CONFIG_KEY = '__global__'  # dump_dir / output_dir etc. (prefs)


def _config_dir():
    """Directory that holds config.json (script dir; cwd fallback)."""
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def face_offsets_path():
    """Path to the config store (config.json, migrated from face_offsets.json)."""
    d = _config_dir()
    new_p = os.path.join(d, CONFIG_FILE)
    old_p = os.path.join(d, OLD_FACE_OFFSETS_FILE)
    # migrate old -> new once
    if not os.path.exists(new_p) and os.path.exists(old_p):
        try:
            # copy, not move, to keep backward compat
            import shutil
            shutil.copy2(old_p, new_p)
        except OSError:
            pass
    # prefer new, fallback to old for reading
    if os.path.exists(new_p):
        return new_p
    if os.path.exists(old_p):
        return old_p
    return new_p


def _load_config_data(path):
    """Load config.json data dict; {} on missing/corrupt."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, ValueError):
        return {}


def _save_config_data(path, data):
    """Atomic-ish save of config.json data dict."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_global_dirs(dump_dir=None, output_dir=None):
    """Persist dump_dir / output_dir to config.json __global__ (any-file config)."""
    path = os.path.join(_config_dir(), CONFIG_FILE)
    # ensure we write to new file even if old exists and new was just migrated
    data = _load_config_data(path)
    # if new empty but old has global, migrate it
    if not data:
        old_p = os.path.join(_config_dir(), OLD_FACE_OFFSETS_FILE)
        if os.path.exists(old_p):
            data = _load_config_data(old_p)
    g = data.get(GLOBAL_CONFIG_KEY)
    if not isinstance(g, dict):
        g = {}
    if dump_dir is not None:
        g['dump_dir'] = str(dump_dir)
    if output_dir is not None:
        g['output_dir'] = str(output_dir)
    data[GLOBAL_CONFIG_KEY] = g
    _save_config_data(path, data)


def load_global_dirs():
    """Return (dump_dir, output_dir) from config.json __global__ or (None, None)."""
    path = face_offsets_path()
    data = _load_config_data(path)
    g = data.get(GLOBAL_CONFIG_KEY)
    if not isinstance(g, dict):
        return None, None
    return g.get('dump_dir'), g.get('output_dir')


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
    # extra_hashes はUIに無い手動データ (face_offsets.json 直編集) なので、
    # 再保存で消えないよう旧 config から引き継ぐ。
    old_cfg = entry.get('__config__')
    if isinstance(old_cfg, dict) and 'extra_hashes' in old_cfg \
            and 'extra_hashes' not in config:
        config['extra_hashes'] = old_cfg['extra_hashes']
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


def units_map_from_config_and_list(props):
    """保存済み config の units と props.units_list をマージして返す。

    units_list 優先 (同じ vb0 は units_list の role が勝つ)。UnitsSave を
    押さなくても追加ユニットが AutoSetup / ImportAll / ImportDump /
    PreviewPair で即座に使われるようにする。
    """
    units = dict(load_char_config(
        face_offsets_path(), props.char_name.strip()).get('units', {}))
    for item in props.units_list:
        units[item.vb0] = item.role
    return units


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
        'shrink_half': [float(v) for v in props.shrink_half],
        'shrink_scale': float(props.shrink_scale),
        'shrink_falloff': float(props.shrink_falloff),
        'shrink_shift': [float(v) for v in props.shrink_shift],
        'face_full_transform': bool(props.face_full_transform),
        'face_offset_eye': [float(v) for v in props.face_offset_eye],
        'face_offset_mouth': [float(v) for v in props.face_offset_mouth],
        'face_offset_brow': [float(v) for v in props.face_offset_brow],
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

    IB-split generic: Body が IB分割 (log.txt に同IBで複数 first_index)の
    場合、偽Body (最大 vb0、vert_count が position_vb と不一致でも) は
    is_fake_body 付きでプレビューに使い、Export は正規 position_vb で行う。
    偽Body はゴミ判定から除外し、units_map に偽 hash が登録されても許容する。

    When units_map is non-empty (per-character {vb0_hash: role} config),
    it is the authoritative character-mesh whitelist: only pairs whose vb0
    is registered are returned, which also drops NPC/effect dumps that the
    heuristic above cannot tell apart. The largest pair is NOT special-cased
    here: a registered dump may contain 4MB-class garbage buffers (e.g.
    Noelle 911ff708) that are not in units, and they must be excluded.
    """
    if units_map:
        # ユニット登録された偽Bodyも許容: そのままプレビューに使い Export は正規に倒す
        return [p for p in pairs if p['vb0'] in units_map]
    if not pairs:
        return []
    # 偽Body はゴミ判定から除外 (IB分割で最大 vb0 が 200k でも Body として保持)
    fake_hashes = {p['vb0'] for p in pairs if p.get('is_fake_body')}
    by_vert = sorted(pairs, key=lambda p: p['vert_count'], reverse=True)
    i = 0
    while i < len(by_vert) - 1:
        first, second = by_vert[i], by_vert[i + 1]
        if first.get('is_fake_body') or first['vb0'] in fake_hashes:
            i += 1
            continue
        if 50 <= second['vert_count'] <= 3000:
            i += 1  # 顔サイズはボディ判定の比較基準にしない
            continue
        if (first['vert_count'] > 50000
                and first['vert_count'] >= 5 * second['vert_count']):
            by_vert.pop(i)  # 4MB クラスゴミ。1 つ戻して再チェック (複数ゴミ対応)
            i = max(0, i - 1)
        else:
            i += 1
    # largest は偽Bodyがあればそれを優先
    fake_largest = next((p for p in by_vert if p.get('is_fake_body')), None)
    largest = fake_largest if fake_largest is not None else by_vert[0]
    out = []
    for p in pairs:
        if p is largest:
            out.append(p)
        elif 50 <= p['vert_count'] <= 3000:
            out.append(p)
    return out


# ===== PROPERTIES (stored on Scene) =====
_dump_cache: dict = {'pairs': []}  # filled by NHS_OT_AnalyzeDump -> scan_dump_dir()
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
    # Generic sanitize for Body (Lanyan fake Body x/y collapsed -> Z only)
    # _sanitize_half maps 0/微小 -> 0.15 so Body shrinks uniformly.
    half_body = _sanitize_half(half)
    scale = self.shrink_scale
    falloff = self.shrink_falloff
    shift = tuple(self.shrink_shift)
    meshes = [o for o in coll.objects if o.type == 'MESH']
    for obj in meshes:
        if is_body_mesh(obj, meshes):
            # BODY: box 内縮小、pivot = box 中央 (v2.0.0 固定) — sanitized half
            preview_shrink_mesh(obj.data, center, half_body, scale,
                                tuple(obj.location), falloff, shift,
                                False, center)
        else:
            # 顔メッシュ: box 内縮小、pivot = box 中央 (hs_face_origin 基準)
            # BODY と同じ box 判定 (center/half) を使い、box 外の頂点は不変
            pivot = _face_shrink_pivot(obj, center)
            if pivot is not None:
                preview_shrink_mesh(obj.data, center, half_body, scale,
                                    tuple(obj.location), falloff, shift,
                                    False, pivot)
                off = _face_offset_for_role(self, obj.get('hs_role'))
                if off is not None:
                    _apply_face_offset(obj, tuple(off))
    _sync_shrink_box(center, half_body)


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
    has_file = _has_registered_units(context.scene.headshrink_props.char_name)
    has_list = False
    try:
        lst = getattr(context.scene.headshrink_props, "units_list", None)
        has_list = bool(lst is not None and len(lst) > 0)
    except Exception:
        pass
    if not (has_file or has_list):
        return  # units 未登録(ファイルにもリストにも無し)なら自動発火しない
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


def _save_prefs(self, context):
    """プロパティ変更時に userpref.blend と config.json へ自動保存。

    .blend を保存しない運用 (launch_blender.bat 起動) でも、dump_dir /
    output_dir の変更が次回起動に引き継がれるようにする。
    config.json への保存は userpref の補助（なんでもあり設定ファイル化）。
    """
    try:
        bpy.ops.wm.save_userpref()
    except Exception:
        pass  # headless / テスト環境では無視
    # config.json (__global__) へも保存
    try:
        prefs = None
        # context経由の正規 prefs
        if context is not None and getattr(context, "preferences", None) is not None:
            try:
                prefs = context.preferences.addons[__name__].preferences
            except Exception:
                prefs = None
        # updateコールバックの self が AddonPreferences 自体の場合
        if prefs is None and hasattr(self, "dump_dir"):
            prefs = self
        if prefs is not None:
            dump_dir = getattr(prefs, "dump_dir", None)
            output_dir = getattr(prefs, "output_dir", None)
            # None は無視、空文字は保存しない
            save_global_dirs(
                dump_dir=dump_dir if dump_dir else None,
                output_dir=output_dir if output_dir else None,
            )
    except Exception:
        pass


def _dump_dir_changed(self, context):
    """dump_dir 変更時: Character 自動反映 + units リセット + 自動セットアップ予約 + userpref 自動保存。"""
    try:
        new_dir = bpy.path.abspath(self.dump_dir) if getattr(self, "dump_dir", None) else ""
        if new_dir and os.path.isdir(new_dir):
            base = os.path.basename(os.path.normpath(new_dir))
            if base.lower().startswith("frameanalysis"):
                base = os.path.basename(os.path.dirname(os.path.normpath(new_dir)))
            if base and context and getattr(context, "scene", None) \
               and hasattr(context.scene, "headshrink_props"):
                props = context.scene.headshrink_props
                if base != props.char_name:
                    props.char_name = base
                # ダンプディレクトリ変更 = キャラ切替とみなし、前キャラの units
                # (vb0 ハッシュ登録) をメモリ上からクリアする。config.json の
                # 保存データは触らない。
                props.units_list.clear()
                props.units_list_index = 0
    except Exception:
        pass
    _dump_dir_update(self, context)
    _save_prefs(self, context)


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
            is_pos = item.pair_name.startswith('position:')
            registered = (not is_pos) and any(
                u.vb0 == item.vb0
                for u in context.scene.headshrink_props.units_list)
            row_icon = ('OUTLINER_DATA_ARMATURE' if is_pos
                        else ('CHECKBOX_HLT' if registered else 'BLANK1'))
            if not registered and not is_pos:
                layout.active = False  # 未登録ペアは行全体を薄く表示
            row = layout.row()
            row.label(text=item.pair_name, icon=row_icon)
            row.label(text=f"{item.vert_count}v")


def _apply_snap_settings(context, enabled):
    """ライブスナップ設定を scene.tool_settings に適用する。

    enabled=True: スナップ ON + FACE / CLOSEST / PROJECT。G キーで顔メッシュを
    移動中に BODY 表面へ吸着する (ライブスナップ)。False: use_snap を OFF に
    するだけで、snap_elements 等は変更しない (他機能への影響を避ける)。
    テストで bpy.context を直接参照しないよう context 引数を使う。
    """
    ts = context.scene.tool_settings
    ts.use_snap = bool(enabled)
    if enabled:
        ts.snap_elements = {'FACE'}
        ts.snap_target = 'CLOSEST'
        ts.use_snap_project = True


def _face_snap_update(self, context):
    """face_snap_enabled 変更時のライブ更新。"""
    _apply_snap_settings(context, self.face_snap_enabled)


class NHSAddonPreferences(bpy.types.AddonPreferences):
    """アドオン全体のグローバル設定 (userpref.blend に保存され再起動後も復元)。

    シーン (.blend) に依存しない設定を置く。mod 出力先はここで管理する
    (旧: シーン props の output_dir。既存 .blend の旧値は引き継がれず
    デフォルトに戻るが仕様として許容)。
    """
    bl_idname = __name__

    output_dir: bpy.props.StringProperty(
        name="Mod Output Dir",
        default=r"G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink\assets\Preview",
        subtype='DIR_PATH',
        update=_save_prefs,
    )
    dump_dir: bpy.props.StringProperty(
        name="Dump Dir",
        description="3DMigoto frame dump directory (vb0/ib .buf files)",
        default=r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\assets\Dump\Noelle",
        subtype='DIR_PATH',
        update=_dump_dir_changed,
    )


class NHSProps(bpy.types.PropertyGroup):  # bpy.types in Blender 5.x (was bpy.props)
    # ---- 3DMigoto dump workflow ----
    position_vs: bpy.props.StringProperty(
        name="Skinning VS Hash",
        description="Vertex shader hash of the skinning (pointlist) pass; "
                    "vb0 files whose name contains -vs=<this>- are the "
                    "pre-skin position buffers (position_vb) that the game "
                    "re-skins every frame (anim-following vb replacement)",
        default=DEFAULT_POSITION_VS,
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
        default=0.3, min=0.0, max=1.0, step=0.01, precision=3,
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
    face_offset_eye: bpy.props.FloatVectorProperty(
        name="Eye Offset",
        description="EYES メッシュの頂点に加算する平行移動 (display 空間)。"
                    "export の display_to_game でゲーム座標に反映される。"
                    "BODY には適用されない",
        size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
        update=_preview_props_update,
    )
    face_offset_mouth: bpy.props.FloatVectorProperty(
        name="Mouth Offset",
        description="MOUTH メッシュの頂点に加算する平行移動 (display 空間)。"
                    "export の display_to_game でゲーム座標に反映される。"
                    "BODY には適用されない",
        size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
        update=_preview_props_update,
    )
    face_offset_brow: bpy.props.FloatVectorProperty(
        name="Brow Offset",
        description="BROW メッシュの頂点に加算する平行移動 (display 空間)。"
                    "export の display_to_game でゲーム座標に反映される。"
                    "BODY には適用されない",
        size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
        update=_preview_props_update,
    )
    face_snap_enabled: bpy.props.BoolProperty(
        name="Face Snap Enabled",
        description="ON: G キーで顔メッシュを移動中、BODY 表面へスナップ"
                    "(ライブスナップ: face snap / closest / project)",
        default=False,
        update=_face_snap_update,
    )


# ===== OPERATORS =====
class NHS_OT_AnalyzeDump(bpy.types.Operator):
    bl_idname = "headshrink.analyze_dump"
    bl_label = "Analyze Dump"
    bl_description = "Scan dump dir for (vb0, ib) pairs and cache them"

    def execute(self, context):
        props = context.scene.headshrink_props
        prefs = context.preferences.addons[__name__].preferences
        dump_dir = bpy.path.abspath(prefs.dump_dir)
        if not os.path.isdir(dump_dir):
            self.report({'ERROR'}, f"Dump dir not found: {dump_dir}")
            return {'CANCELLED'}
        # 再読み込み: 前回キャッシュをクリアして毎回フルスキャン
        global _last_auto_setup_dir, _last_preview_pair
        _last_auto_setup_dir = None
        _last_preview_pair = None
        _dump_cache['pairs'] = []
        _dump_cache['position_vb'] = {}
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
        # スキニング前 position バッファ (IB 無し) も参考表示
        for h, info in _dump_cache.get('position_vb', {}).items():
            item = props.dump_pairs.add()
            item.pair_name = f"position: {h}"
            item.vb0 = h
            item.ib = ''
            item.vert_count = info['vert_count']
        if not pairs:
            self.report({'WARNING'}, f"No vb0/ib pairs found in {dump_dir}")
            return {'FINISHED'}
        props.dump_pair = 'NONE'
        self.report({'INFO'}, f"Found {len(pairs)} vb0/ib pairs "
                              f"(e.g. {pairs[0]['vb0'][:8]}/{pairs[0]['ib'][:8]} "
                              f"{pairs[0]['vert_count']}v)")
        # セカンダリ VB を units に自動追加 (CopyDispatch を自動生成するため)。
        # キャラロード直後のフレームだけ使われる口などのセカンダリ VB を
        # 登録しておくと、ロード直後に素のメッシュが一瞬表示される既知バグを防げる。
        units = units_map_from_config_and_list(props)
        secondary = find_secondary_vb0s(pairs, units)
        added_items = []
        for vb0, role in secondary.items():
            if any(item.vb0 == vb0 for item in props.units_list):
                continue
            item = props.units_list.add()
            item.vb0 = vb0
            item.role = role
            added_items.append((vb0, role))
        if added_items:
            detail = ", ".join(f"{v} ({r})" for v, r in added_items)
            self.report({'INFO'},
                        f"Secondary VB {len(added_items)} 件を units に自動追加: "
                        f"{detail}")
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
        # position_vb は draw_vb と別物: 通常は draw_vb を BODY 登録すれば
        # 自動対応付けされる (直接登録は必須でない)
        note = ("position_vb はスキニング前バッファ。通常フローでは "
                "draw_vb を BODY 登録すれば自動対応付けされます") \
            if sel.pair_name.startswith('position:') \
            else "保存して ③ セットアップで表示"
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
                              f"{note}")
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


def _import_pair(context, pair, units_map=None):
    """Import one dump pair into HeadShrink_Dump with role assignment.

    Replaces any existing Dump_<vb0> object. Adds hs_original_pos + the
    hs_vb0_hash/hs_ib_hash/hs_vert_count/hs_role custom properties. Role comes
    from the per-character units map first, else largest pair = BODY, else
    OTHER. A BODY pair with a matching position_vb is loaded from the pre-skin
    buffer (hs_position_vb set) so the preview shows the posed shape. Returns
    (obj, role, nverts, ntris, max_index); raises OSError/
    ValueError on load failure.
    """
    if units_map is None:
        units_map = {}
    # ゴミ除外後の選択候補基準で最大判定 (ゴミが最大でも真のボディが BODY になる)
    candidates = select_import_pairs(_dump_cache['pairs'], units_map)
    is_largest = all(pair['vert_count'] >= p['vert_count']
                     for p in candidates)
    role = role_for_pair(pair['vb0'], pair['vert_count'], units_map, is_largest)
    # BODY + position_vb 対応: スキニング前 position バッファから読込 (頂点数
    # 同一なので IB は draw 側を流用)。position_vb は毎フレーム再スキニング
    # されるため、プレビューは直立ポーズではなくポーズ反映済み形状になる。
    # IB分割汎用: is_fake_body または IB分割+vert不一致なら偽Bodyを x,y=0 で
    # プレビューし、Export は正規 position_vb で行う (偽 vb0 は export に使わない)。
    is_fake = bool(pair.get('is_fake_body')) or (
        role == 'BODY' and _is_fake_body_pair(pair, _dump_cache))
    # units_map に偽Body hash が BODY 登録されても許容 (そのままプレビュー、Exportは正規)
    if role == 'BODY' and not is_fake and pair['vb0'] in (units_map or {}):
        if _has_ib_split(_dump_cache.get('ib_splits') or {}) and _is_fake_body_pair(pair, _dump_cache):
            is_fake = True
    vb0_path = pair['vb0_path']
    transform = game_to_display
    position_vb = None
    real_for_fake = None
    if role == 'BODY' and is_fake:
        # プレビューは偽Body (最大 vb0) をそのまま x,y=0 で表示
        real_for_fake = _find_real_position_vb(_dump_cache.get('position_vb') or {})
        if real_for_fake is None:
            real_for_fake = _dump_cache.get('real_position_vb')
        # transform は game_to_display のまま (偽は position_vb ではない)
    elif role == 'BODY':
        position_vb = find_position_vb(_dump_cache, pair['vb0'],
                                       pair['vert_count'])
        if position_vb is not None:
            vb0_path = position_vb['path']
            # position_vb is y-up model-local, not game space
            transform = position_vb_to_display
    verts, faces, max_index = load_dump_mesh(
        vb0_path, pair['ib_path'], transform=transform)
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
    obj["hs_role"] = role
    if position_vb is not None:
        obj["hs_position_vb"] = position_vb['vb_hash']
    if is_fake:
        obj["hs_is_fake_body"] = True
        # Export は正規 position_vb を使うため real hash を保持
        rh = pair.get('real_vb_hash') or (real_for_fake or {}).get('vb_hash')
        if rh:
            obj["hs_real_position_vb"] = rh
        # プレビューは x,y=0 に置くだけ (偽Bodyは原点で表示、後段の auto-place で動かさない)
        obj.location = (0.0, 0.0, 0.0)
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
        units_map = units_map_from_config_and_list(props)
        try:
            obj, role, nv, nf, mi = _import_pair(context, pair, units_map)
        except (OSError, ValueError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Imported {obj.name}: {nv} verts, "
                              f"{nf} tris (role {role}, max index {mi})"
                              + (f" (position_vb {obj['hs_position_vb']}: "
                                 "ポーズ反映済み形状)" if obj.get('hs_position_vb') else ""))
        return {'FINISHED'}


class NHS_OT_ImportAll(bpy.types.Operator):
    bl_idname = "headshrink.import_all"
    bl_label = "Import All"
    bl_description = "Auto-import the body (largest pair) + face-sized pairs (50..3000 verts)"

    def execute(self, context):
        props = context.scene.headshrink_props
        units_map = units_map_from_config_and_list(props)
        pairs = select_import_pairs(_dump_cache['pairs'], units_map)
        if not pairs:
            self.report({'ERROR'}, "Run Analyze Dump first (no candidate pairs)")
            return {'CANCELLED'}
        imported = 0
        failed = 0
        pv_imports = 0
        for pair in pairs:
            try:
                obj, *_ = _import_pair(context, pair, units_map)
                imported += 1
                if obj.get('hs_position_vb'):
                    pv_imports += 1
            except (OSError, ValueError):
                failed += 1
        pv_note = f"; {pv_imports} via position_vb" if pv_imports else ""
        self.report({'INFO'}, f"Imported {imported} mesh(es) into "
                              f"{DUMP_COLLECTION} (skipped {failed} failed)"
                              f"{pv_note}")
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
        prefs = context.preferences.addons[__name__].preferences
        dump_dir = bpy.path.abspath(prefs.dump_dir)
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
        units_map = units_map_from_config_and_list(props)
        pairs = select_import_pairs(_dump_cache['pairs'], units_map)
        imported = 0
        failed = 0
        pv_imports = 0
        for pair in pairs:
            try:
                obj, *_ = _import_pair(context, pair, units_map)
                imported += 1
                if obj.get('hs_position_vb'):
                    pv_imports += 1
            except (OSError, ValueError):
                failed += 1
        # Preview Setup 相当 (共通実装)
        result = _preview_setup_impl(self, context)
        if result != {'FINISHED'}:
            return result
        # スナップ ON 設定を再適用 (シーン再構築後もトグル ON 状態を保証)
        if props.face_snap_enabled:
            _apply_snap_settings(context, True)
        # Load Default を最後に適用 (AutoSetup完了時にデフォルト設定を読み込む)
        try:
            _def_cfg = load_char_config(face_offsets_path(), DEFAULT_CONFIG_KEY)
            if _def_cfg:
                apply_char_config(props, _def_cfg)
        except Exception:
            pass
        pv_note = f"; {pv_imports} via position_vb" if pv_imports else ""
        self.report({'INFO'}, f"Auto setup: {removed} object(s) cleared, "
                              f"{imported} mesh(es) imported ({failed} failed), "
                              f"preview ready{pv_note}")
        return {'FINISHED'}


def _match_face_offsets(body_mesh, face_objs, initial_locs,
                        dist_threshold=0.02, max_iter=6, tol=0.0005):
    """顔メッシュの配置オフセットを body との境界マッチングで自動計算。

    顔メッシュの表示頂点 (v.co + loc) から最近傍の body 頂点を探し、
    境界ペア (距離 < dist_threshold) の位置差 (body - 顔) の各軸中央値で
    loc を反復更新して収束させる。顔メッシュが body と正しく噛み合う
    配置 (loc) を求める (保存済み face_offsets の無いメッシュ向け)。

    body_mesh: BODY ロールの bpy オブジェクト (表示頂点 = v.co + obj.location)
    face_objs: 顔メッシュの bpy オブジェクト群 (location は (0,0,0) 想定)
    initial_locs: {vb0_hash: (x, y, z)} 従来の head_center - face_center 値
    戻り値: {vb0_hash: (x, y, z)} 収束 loc (収束しなくても max_iter 後の値)
    """
    if np is None:
        return dict(initial_locs)
    body_pts = np.asarray(
        [tuple(v.co) for v in body_mesh.data.vertices], dtype=np.float64)
    if len(body_pts) == 0:
        return {}
    body_pts += np.asarray(tuple(body_mesh.location), dtype=np.float64)
    out = {}
    for o in face_objs:
        vb0 = str(o.get('hs_vb0_hash', ''))
        face_pts = np.asarray(
            [tuple(v.co) for v in o.data.vertices], dtype=np.float64)
        if len(face_pts) == 0:
            continue
        loc = np.asarray(initial_locs.get(vb0, (0.0, 0.0, 0.0)),
                         dtype=np.float64)
        for _ in range(max_iter):
            disp = face_pts + loc  # 顔メッシュの表示頂点 (n,3)
            # 最近傍 body 頂点をチャンク処理で探索 (メモリ爆発防止)。
            # 顔頂点を 256 個ずつに分け、各チャンクで距離計算 + argmin。
            diffs = []
            for start in range(0, len(disp), 256):
                chunk = disp[start:start + 256]
                d = chunk[:, None, :] - body_pts[None, :, :]
                dist2 = np.einsum('ijk,ijk->ij', d, d)
                nearest = np.argmin(dist2, axis=1)
                dmin = np.sqrt(dist2[np.arange(chunk.shape[0]), nearest])
                mask = dmin < dist_threshold
                if mask.any():
                    diffs.append(body_pts[nearest[mask]] - chunk[mask])
            if not diffs:
                break  # 境界ペア 0 件 → loc 不変で停止
            med = np.median(np.concatenate(diffs, axis=0), axis=0)
            loc = loc + med  # 外れ値に強い中央値で更新
            if np.max(np.abs(med)) < tol:
                break  # 収束
        out[vb0] = tuple(float(c) for c in loc)
    return out


def _face_draw_to_body_space(face_mesh, body_draw_verts, body_pos_verts,
                             dist_threshold=0.02):
    """顔メッシュ (draw_vb 空間) を position_vb 空間に近似配置する loc を計算。

    BODY の draw_vb と position_vb は同一頂点数・頂点順序対応 (両方ダンプ
    由来、同一フレーム)。各顔頂点について body_draw の最近傍頂点 i を
    チャンク探索 (256 個ずつ) で求め、境界ペア (距離 < dist_threshold) の
    スキニング変位 disp = body_pos[i] - body_draw[i] を収集し、その中央値を
    loc として返す (外れ値に強い)。顔メッシュの v.co は draw_vb 空間のまま
    で、配置は obj.location で表現する (export は v.co のみ使用 → loc 独立)。

    face_mesh: 顔メッシュの bpy オブジェクト (v.co は draw_vb 表示空間)
    body_draw_verts: BODY draw_vb の表示頂点リスト (game_to_display 適用済み)
    body_pos_verts: BODY position_vb の表示頂点リスト (position_vb_to_display
                    適用済み)。body_draw_verts と同数・同順序
    戻り値: (x, y, z) tuple または None (np 無し / 入力空 / 境界ペア 0 件)
    """
    if np is None:
        return None
    face_pts = np.asarray([tuple(v.co) for v in face_mesh.data.vertices],
                          dtype=np.float64)
    body_draw = np.asarray(body_draw_verts, dtype=np.float64)
    body_pos = np.asarray(body_pos_verts, dtype=np.float64)
    if len(face_pts) == 0 or len(body_draw) == 0:
        return None
    if body_draw.shape != body_pos.shape:
        return None
    # 各顔頂点の最近傍 body_draw 頂点をチャンク探索 (メモリ爆発防止)。
    # _match_face_offsets と同じ手法: chunk[:, None, :] - body[None, :, :]
    # → einsum 距離 → argmin。
    diffs = []
    for start in range(0, len(face_pts), 256):
        chunk = face_pts[start:start + 256]
        d = chunk[:, None, :] - body_draw[None, :, :]
        dist2 = np.einsum('ijk,ijk->ij', d, d)
        nearest = np.argmin(dist2, axis=1)
        dmin = np.sqrt(dist2[np.arange(chunk.shape[0]), nearest])
        mask = dmin < dist_threshold
        if mask.any():
            diffs.append(body_pos[nearest[mask]] - chunk[mask])
    if not diffs:
        return None  # 境界ペア 0 件 → 配置不能
    loc = np.median(np.concatenate(diffs, axis=0), axis=0)
    return tuple(float(c) for c in loc)


def _load_body_draw_verts(main):
    """BODY の draw_vb 表示頂点をダンプから再読込する。

    position_vb 空間の v.co とは別空間 (draw_vb) のため、顔メッシュの近似
    配置 (_face_draw_to_body_space) にはダンプの vb0 を game_to_display
    変換して使う。ペア未解析 / 読込失敗時は None。
    """
    pair = next((p for p in _dump_cache['pairs']
                 if p['vb0'] == str(main.get('hs_vb0_hash', ''))), None)
    if pair is None:
        return None
    try:
        verts, _, _ = load_dump_mesh(pair['vb0_path'], pair['ib_path'],
                                     transform=game_to_display)
    except (OSError, ValueError):
        return None
    return verts


def _face_bbox_center(meshes):
    """Display-space bbox center (x, y, z) over placed face meshes.

    Face mesh = non-BODY (is_body_mesh False) with a non-zero location
    (auto-placed by _preview_setup_impl; unplaced dump copies sit at
    (0,0,0) and are excluded). Coordinates are display space (v.co +
    obj.location). Returns None when no such mesh.
    """
    placed = [o for o in meshes
              if not is_body_mesh(o, meshes)
              and tuple(o.location) != (0.0, 0.0, 0.0)]
    if not placed:
        return None
    mins = [float('inf')] * 3
    maxs = [-float('inf')] * 3
    for o in placed:
        off = tuple(o.location)
        for v in o.data.vertices:
            for i in range(3):
                c = v.co[i] + off[i]
                if c < mins[i]:
                    mins[i] = c
                if c > maxs[i]:
                    maxs[i] = c
    return tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))


def _face_mesh_center(mesh):
    """顔メッシュ自身の縮小中心 = 表示空間 bbox 中心 (x, y, z)。

    基準は hs_original_pos 属性 (あれば) + obj.location、無ければ v.co +
    obj.location。全頂点の bbox 中心を返す。頂点 0 件なら None。

    preview_shrink_mesh は display 空間 (v.co + offset) で縮小し v.co に
    書き戻すため、center に表示空間中心を渡すとローカル空間では
    hs_original_pos の bbox 中心基準になり loc 非依存 (export 分離保証)。
    """
    attr = mesh.data.attributes.get('hs_original_pos')
    off = tuple(mesh.location)
    mins = [float('inf')] * 3
    maxs = [-float('inf')] * 3
    n = 0
    if attr is not None:
        flat = [0.0] * (len(mesh.data.vertices) * 3)
        attr.data.foreach_get('vector', flat)
        for i in range(0, len(flat), 3):
            for j in range(3):
                c = flat[i + j] + off[j]
                if c < mins[j]:
                    mins[j] = c
                if c > maxs[j]:
                    maxs[j] = c
            n += 1
    else:
        for v in mesh.data.vertices:
            for j in range(3):
                c = v.co[j] + off[j]
                if c < mins[j]:
                    mins[j] = c
                if c > maxs[j]:
                    maxs[j] = c
            n += 1
    if n == 0:
        return None
    return tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))


def _face_shrink_pivot(obj, center):
    """顔メッシュ縮小の pivot (表示空間) を返す。

    hs_face_origin (配置時の obj.location) があれば、box 中央を顔ローカル
    空間に変換 (center - origin) してから現在の配置位置で表示空間に戻す
    (center - origin + obj.location)。配置位置が変わってもローカル pivot は
    不変なので export (v.co のみ使用) と分離できる。配置位置のままなら
    pivot == center (BODY と同じ box 中央)。hs_face_origin が無い場合は
    従来どおり _face_mesh_center (表示空間 bbox 中心) にフォールバック。
    """
    origin = obj.get('hs_face_origin')
    if origin is not None:
        return tuple(center[i] - origin[i] + obj.location[i]
                     for i in range(3))
    return _face_mesh_center(obj)


def _face_offset_for_role(props, role):
    """ロールに応じた face_offset プロパティ値を返す。

    EYES/MOUTH/BROW はそれぞれ専用プロパティ (face_offset_eye/mouth/brow) を
    返す。それ以外 (OTHER 等) は None (オフセット適用なし)。
    """
    mapping = {
        'EYES': getattr(props, 'face_offset_eye', None),
        'MOUTH': getattr(props, 'face_offset_mouth', None),
        'BROW': getattr(props, 'face_offset_brow', None),
    }
    return mapping.get(role)


def _apply_face_offset(obj, offset):
    """顔メッシュの v.co に face_offset を加算 (display 空間、export に反映)。

    BODY には適用しない (呼び出し側で顔メッシュのみに呼ぶ)。全ゼロなら
    何もしない (無駄な頂点走査を避ける)。preview_shrink_mesh の後に呼ぶ
    ことで、縮小結果に平行移動を重ねる (非累積)。
    """
    if not any(offset):
        return
    for v in obj.data.vertices:
        v.co = (v.co[0] + offset[0], v.co[1] + offset[1],
                v.co[2] + offset[2])


def _sanitize_half(half, fallback=0.15):
    """Per-axis sanitize: non-finite / <=1e-6 / >5.0 -> fallback, else clamp to >=fallback.

    Generic fallback for e.g. Lanyan fake Body (x/y collapsed -> Z only) or
    gargage buffers: any degenerated axis gets fallback so shrink_positions
    never sees a thin slab. No character-name branching.
    """
    out = []
    for h in half:
        if not math.isfinite(h) or h <= 1e-6 or h > 5.0:
            out.append(fallback)
        elif h < fallback:
            out.append(fallback)
        else:
            out.append(h)
    return tuple(out)


def _body_head_bbox(meshes, head_fraction=0.35):
    """Display-space bbox (center, half) of the BODY mesh's head region.

    BODY is in position_vb space (z 0..1.6, head near the top) since
    v1.9.0; the head region is the top head_fraction of its z range.
    Returns ((cx, cy, cz), (hx, hy, hz)) or None when no BODY mesh.
    NaN/inf vertices (garbage buffers like 911ff708) are ignored so the
    box never becomes degenerate or infinite.
    Generic IB-split fake Body (e.g. Lanyan d3569268 220k) is read via
    game_to_display while real Body is position_vb_to_display — bbox
    from the fake would be garbage / collapsed (x/y ~0 -> Z only), so
    when hs_is_fake_body is set we derive bbox from the real
    position_vb instead (no hard-coded hash).
    """
    body = next((o for o in meshes if is_body_mesh(o, meshes)), None)
    if body is None:
        return None
    # Fake Body generic path: derive bbox from real position_vb (correct space)
    if bool(body.get('hs_is_fake_body')):
        try:
            real = _find_real_position_vb(_dump_cache.get('position_vb') or {}) or _dump_cache.get('real_position_vb')
            if real and real.get('path') and os.path.exists(real['path']):
                with open(real['path'], 'rb') as _f:
                    _d = _f.read()
                _n = len(_d) // DUMP_STRIDE
                _verts = [position_vb_to_display(struct.unpack_from('<3f', _d, i * DUMP_STRIDE)) for i in range(_n)]
                _zs = [v[2] for v in _verts if all(math.isfinite(c) for c in v)]
                if _zs and abs(max(_zs) - min(_zs)) > 1e-6:
                    _z_min, _z_max = min(_zs), max(_zs)
                    _z_thresh = _z_min + (1.0 - head_fraction) * (_z_max - _z_min)
                    _mins = [float('inf')] * 3
                    _maxs = [-float('inf')] * 3
                    _n2 = 0
                    for v in _verts:
                        if not all(math.isfinite(x) for x in v):
                            continue
                        if v[2] < _z_thresh:
                            continue
                        _n2 += 1
                        for i in range(3):
                            if v[i] < _mins[i]:
                                _mins[i] = v[i]
                            if v[i] > _maxs[i]:
                                _maxs[i] = v[i]
                    if _n2:
                        _center = tuple((_mins[i] + _maxs[i]) / 2.0 for i in range(3))
                        _half = tuple((_maxs[i] - _mins[i]) / 2.0 for i in range(3))
                        if all(math.isfinite(x) for x in _center + _half):
                            return _center, _sanitize_half(_half)
        except Exception:
            pass
    off = tuple(body.location)
    # finite z only (ignore garbage / NaN)
    zs = [v.co[2] + off[2] for v in body.data.vertices
          if all(math.isfinite(v.co[i]) for i in range(3))]
    if not zs:
        return None
    # guard against degenerate / infinite range (garbage)
    if not all(math.isfinite(c) for c in zs):
        return None
    z_min, z_max = min(zs), max(zs)
    if not (math.isfinite(z_min) and math.isfinite(z_max)):
        return None
    # degenerate height (all z equal) -> no head region to isolate
    if abs(z_max - z_min) < 1e-6:
        return None
    z_thresh = z_min + (1.0 - head_fraction) * (z_max - z_min)
    mins = [float('inf')] * 3
    maxs = [-float('inf')] * 3
    n = 0
    for v in body.data.vertices:
        if not all(math.isfinite(v.co[i]) for i in range(3)):
            continue
        c = (v.co[0] + off[0], v.co[1] + off[1], v.co[2] + off[2])
        if not all(math.isfinite(x) for x in c):
            continue
        if c[2] < z_thresh:
            continue
        n += 1
        for i in range(3):
            if c[i] < mins[i]:
                mins[i] = c[i]
            if c[i] > maxs[i]:
                maxs[i] = c[i]
    if n == 0:
        return None
    if not all(math.isfinite(mins[i]) and math.isfinite(maxs[i]) for i in range(3)):
        return None
    center = tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))
    half = tuple((maxs[i] - mins[i]) / 2.0 for i in range(3))
    if not all(math.isfinite(x) for x in center + half):
        return None
    return center, half


def _auto_face_shrink_center(props, meshes):
    """Set shrink_center/half so the box covers the BODY head.

    Box = center ± half, sized from the BODY head bbox (half clamped to
    >= 0.15 per axis so the box never collapses). Falls back to the
    face-mesh bbox (center z + 0.1, half untouched) when no BODY mesh
    exists. No candidate -> untouched.

    Generic fallback: if the BODY bbox is degenerate (any half <=1e-6,
    non-finite, or absurdly large >5.0 — e.g. Lanyan fake Body 220k vs
    real 28k mismatch or garbage buffers with inf), use the default half
    0.15 on all axes instead of propagating a collapsed / huge box. This
    keeps face shrink uniform and avoids the "Z only" artefact where
    shrink_positions would ignore a zero-thickness axis. No character-name
    branching.
    """
    head = _body_head_bbox(meshes)
    # Generic fake-Body handling: fake Body (e.g. d3569268 220k stride92) は
    # 誤stride読込でゴミbboxになるため、正規position_vbの頭部中心で上書きする。
    # Lanyanハードコード無し、任意のIB分割偽Bodyで有効。
    if head is not None:
        try:
            body_mesh = next((m for m in meshes if is_body_mesh(m, meshes)), None)
            if body_mesh is not None and bool(body_mesh.get('hs_is_fake_body')):
                real = _find_real_position_vb(_dump_cache.get('position_vb') or {}) or _dump_cache.get('real_position_vb')
                if real and real.get('path') and os.path.exists(real['path']):
                    with open(real['path'], 'rb') as _f:
                        _d = _f.read()
                    _n = len(_d) // DUMP_STRIDE
                    _verts = [position_vb_to_display(struct.unpack_from('<3f', _d, i * DUMP_STRIDE)) for i in range(_n)]
                    _rc = head_center_from_verts(_verts)
                    if _rc is not None and all(math.isfinite(c) for c in _rc):
                        center, half = _rc, (0.15, 0.15, 0.15)
                        props.shrink_center = center
                        props.shrink_half = half
                        return
        except Exception:
            pass
    if head is not None:
        center, half = head
        # center must be finite
        if not all(math.isfinite(c) for c in center):
            head = None
        elif not all(math.isfinite(h) for h in half):
            head = None
        # half is already sanitized by _body_head_bbox / _sanitize_half, but
        # keep per-axis fallback when raw half slipped through (e.g. direct call)
        elif any(h <= 1e-6 or h > 5.0 for h in half):
            props.shrink_center = center
            props.shrink_half = _sanitize_half(half)
            return
        else:
            props.shrink_center = center
            props.shrink_half = _sanitize_half(half)
            return
    face_c = _face_bbox_center(meshes)
    if face_c is not None:
        props.shrink_center = (props.shrink_center[0], face_c[1], face_c[2] + 0.1)


def _median(values):
    """数値リストの中央値を返す (偶数個は中間2つの平均、空は 0.0)。"""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


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
        # 偽Bodyフラグはプレビューまで引き継ぐ (Exportで正規 position_vb に倒すため)
        if s.get('hs_is_fake_body'):
            obj["hs_is_fake_body"] = True
            if s.get('hs_real_position_vb'):
                obj["hs_real_position_vb"] = s["hs_real_position_vb"]
        if s.get('hs_position_vb'):
            obj["hs_position_vb"] = s["hs_position_vb"]
        if s.get('hs_ib_hash'):
            obj["hs_ib_hash"] = s["hs_ib_hash"]
        if s.get('hs_vert_count'):
            obj["hs_vert_count"] = s["hs_vert_count"]
        coll.objects.link(obj)
    # 偽Bodyは x,y=0 に置くだけ (汎用 IB分割対応)
    for o in [x for x in coll.objects if x.get('hs_is_fake_body')]:
        o.location = (0.0, 0.0, 0.0)
    # Auto-place shared face units onto the body's head: the face VBs are
    # character-shared and dumped in their own local space, so they appear
    # near the waist. Offset each by (head_center - face_center) on the
    # object location (display coords; user can still tweak with G).
    preview_objs = [o for o in coll.objects if o.type == 'MESH']
    if preview_objs:
        body_objs = [o for o in preview_objs if o.get('hs_role') == 'BODY']
        main = body_objs[0] if body_objs else max(
            preview_objs, key=lambda o: len(o.data.vertices))
        # BODY が position_vb 空間 (hs_position_vb あり) の場合、顔メッシュ
        # (draw_vb 空間) は最近傍スキニング変位加算で position_vb 空間に
        # 近似配置する。BODY の draw_vb 頂点はダンプから再読込する
        # (position_vb 空間の v.co とは別空間のため)。ペアが見つからない /
        # 読込失敗時は従来の head_center 配置にフォールバック。
        # 偽Bodyは position_vb を持たず x,y=0 のままなので PV配置はスキップ
        use_pv_placement = bool(main.get('hs_position_vb')) and not bool(main.get('hs_is_fake_body'))
        body_draw_verts = None
        body_pos_verts = None
        if use_pv_placement:
            body_draw_verts = _load_body_draw_verts(main)
            if body_draw_verts:
                body_pos_verts = [tuple(v.co) for v in main.data.vertices]
            else:
                use_pv_placement = False
        locs = []
        if use_pv_placement:
            # 顔メッシュを draw_vb → position_vb 空間に近似配置 (loc のみ変更、
            # v.co は draw_vb 空間のまま → export は loc と独立)。
            for o in preview_objs:
                if o is main:
                    continue
                loc = _face_draw_to_body_space(o, body_draw_verts,
                                               body_pos_verts)
                if loc is not None:
                    locs.append(loc)
        if use_pv_placement and locs:
            # 目/口/眉は同一 draw_vb 空間・同一親トランスフォームで描画される
            # ため、各顔の個別 loc の中央値を共通移動量として全顔に適用する
            # (口は表情で形状が変わるため個別計算だとズレるが、共通化で平均化)。
            # x は左右対称のため常に 0.0 に固定 (計算値だとバラつく)。
            common_loc = (0.0,
                          0.0,
                          _median([loc[2] for loc in locs]))
            for o in preview_objs:
                if o is main:
                    continue
                o.location = common_loc
        else:
            # Fake Body (IB分割で最大vb0=220k等が偽) は誤ったstrideで読まれゴミ座標
            # になるため、正規position_vbの頭部中心を優先して使う (generic)。
            if bool(main.get('hs_is_fake_body')):
                head_center = None
                try:
                    real = _find_real_position_vb(_dump_cache.get('position_vb') or {}) or _dump_cache.get('real_position_vb')
                    if real and real.get('path') and os.path.exists(real['path']):
                        with open(real['path'], 'rb') as _f:
                            _d = _f.read()
                        _n = len(_d) // DUMP_STRIDE
                        _verts = [position_vb_to_display(struct.unpack_from('<3f', _d, i * DUMP_STRIDE)) for i in range(_n)]
                        head_center = head_center_from_verts(_verts)
                except Exception:
                    head_center = None
                if head_center is None:
                    head_center = head_center_from_verts([tuple(v.co) for v in main.data.vertices])
            else:
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
                    if use_pv_placement:
                        # PVフォールバック: x,yは0固定 (対称性維持)
                        o.location = (0.0, 0.0, head_center[2] - face_center[2])
                    else:
                        o.location = tuple(head_center[i] - face_center[i] for i in range(3))
        # 顔メッシュは draw_vb 空間で描画されるため、プレビュー表示用に
        # Z 軸 180° 回転を適用する (export は v.co のみ使用するため mod には影響しない)。
        for o in preview_objs:
            if o is not main:
                o.rotation_euler = (0.0, 0.0, math.pi)
        # Re-apply saved per-character face offsets if any (overrides auto
        # placement with the user's G-key tweaks from a previous session).
        saved = load_face_offsets(face_offsets_path(),
                                  context.scene.headshrink_props.char_name)
        for o in preview_objs:
            if o.name in saved:
                o.location = tuple(saved[o.name])
        # 境界マッチング: 保存済み offsets の無い顔メッシュのみ、body との
        # 最近傍境界ペアから収束 loc を自動計算して適用 (保存値は従来通り
        # 優先。収束値は JSON には保存せず、毎回 auto_setup で再計算)。
        # position_vb 配置時は空間が異なるため実行しない (無意味)。
        if not use_pv_placement:
            face_objs = [o for o in preview_objs
                         if o is not main and o.name not in saved]
            if face_objs:
                initial_locs = {o.get('hs_vb0_hash', ''): tuple(o.location)
                                for o in face_objs}
                matched = _match_face_offsets(main, face_objs, initial_locs)
                for o in face_objs:
                    loc = matched.get(o.get('hs_vb0_hash', ''))
                    if loc is not None:
                        o.location = loc
        # Record the final placement (after auto-placement + saved offsets)
        # so Reset Preview can restore G-key moved faces to the setup-time
        # position. Stored per-vertex (POINT domain) like hs_original_pos;
        # read back via data[0].vector.
        for o in preview_objs:
            loc = tuple(o.location)
            attr = o.data.attributes.new(
                name='hs_original_loc', type='FLOAT_VECTOR', domain='POINT')
            attr.data.foreach_set('vector', list(loc) * len(o.data.vertices))
            # 顔メッシュ (main 以外) は配置位置を hs_face_origin として保存。
            # 縮小 pivot は box 中央をこの原点基準で顔ローカル空間に変換して
            # 使う (_face_shrink_pivot)。G キーで動かしてもローカル pivot は
            # 不変のため export (v.co のみ) と分離できる。
            if o is not main:
                o['hs_face_origin'] = tuple(o.location)
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
    # 自動設定 (BODY 頭部 bbox 基準; BODY 無しは配置済み顔メッシュ基準):
    # box 中心 (shrink_center) は顔面 bbox 中心 z を 0.1 上へシフト →
    # box 下端が首より上になり、「体が小さくなる」問題を回避。
    # 縮小中心 (pivot) は box 中央に固定 (v2.0.0: 自動設定しない)。
    # 顔メッシュ無しなら触らない。HS_ShrinkBox はこの center で作られる
    # ため、設定後に呼ぶこと。
    _auto_face_shrink_center(props, preview_objs)
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
        units_map = units_map_from_config_and_list(props)
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
        half_body = _sanitize_half(half)
        scale = props.shrink_scale
        falloff = props.shrink_falloff
        shift = tuple(props.shrink_shift)
        meshes = [o for o in coll.objects if o.type == 'MESH']
        count = 0
        for obj in meshes:
            if is_body_mesh(obj, meshes):
                # BODY: sanitized half (0/微小 -> 0.15) for uniform shrink
                if preview_shrink_mesh(obj.data, center, half_body, scale,
                                       tuple(obj.location), falloff, shift,
                                       False, center):
                    count += 1
            else:
                # 顔メッシュ: 同じ sanitized box で判定
                pivot = _face_shrink_pivot(obj, center)
                if pivot is not None and preview_shrink_mesh(
                        obj.data, center, half_body, scale, tuple(obj.location),
                        falloff, shift, False, pivot):
                    count += 1
                    off = _face_offset_for_role(props, obj.get('hs_role'))
                    if off is not None:
                        _apply_face_offset(obj, tuple(off))
        self.report({'INFO'}, f"Preview shrink applied to {count} mesh(es) "
                              f"(scale={scale:.3f})")
        return {'FINISHED'}


class NHS_OT_RepositionFaces(bpy.types.Operator):
    bl_idname = "headshrink.reposition_faces"
    bl_label = "Reposition Faces"
    bl_description = "Re-run draw->body space placement on the selected face meshes (all if none selected)"

    def execute(self, context):
        if bpy.context.mode == 'EDIT_MESH':
            self.report({'ERROR'},
                        "Edit モード中は実行できません。Edit モードを終了してから実行してください")
            return {'CANCELLED'}
        coll = bpy.data.collections.get(PREVIEW_COLLECTION)
        if coll is None:
            self.report({'ERROR'}, f"No {PREVIEW_COLLECTION} collection (Preview Setup first)")
            return {'CANCELLED'}
        meshes = [o for o in coll.objects if o.type == 'MESH']
        if not meshes:
            self.report({'ERROR'}, f"No meshes in {PREVIEW_COLLECTION}")
            return {'CANCELLED'}
        # BODY は _preview_setup_impl と同じ判定 (hs_role 優先、無ければ最大頂点数)
        body_objs = [o for o in meshes if o.get('hs_role') == 'BODY']
        main = body_objs[0] if body_objs else max(
            meshes, key=lambda o: len(o.data.vertices))
        faces = [o for o in meshes if not is_body_mesh(o, meshes)]
        if not faces:
            self.report({'WARNING'}, "No face meshes in preview")
            return {'FINISHED'}
        # 選択中の顔メッシュのみ対象 (何も選択されていなければ全部)
        selected = [o for o in faces if o.select_get()]
        targets = selected if selected else faces
        body_draw_verts = _load_body_draw_verts(main)
        if body_draw_verts is None:
            self.report({'ERROR'},
                        "BODY draw_vb をダンプから読込めません (ペア未解析 or 読込失敗)。"
                        "先に ① 解析 → ③ セットアップを実行してください")
            return {'CANCELLED'}
        body_pos_verts = [tuple(v.co) for v in main.data.vertices]
        count = 0
        for o in targets:
            loc = _face_draw_to_body_space(o, body_draw_verts, body_pos_verts)
            if loc is None:
                continue
            o.location = loc
            # 縮小 pivot の基準も新配置に更新 (以後の _face_shrink_pivot は
            # この原点基準で box 中央をローカル変換する)
            o['hs_face_origin'] = tuple(loc)
            count += 1
        self.report({'INFO'}, f"Repositioned {count}/{len(targets)} face mesh(es)")
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

    def invoke(self, context, event):
        char_name = context.scene.headshrink_props.char_name.strip() or 'Char'
        path = face_offsets_path()
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict) and char_name in data:
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

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

    def invoke(self, context, event):
        path = face_offsets_path()
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict) and DEFAULT_CONFIG_KEY in data:
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

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
    bl_description = "Write <char><Unit> Position/Base/Key.buf + <char>Head.hlsl + <char>.ini (VB Replace or CopyDispatch)"

    def execute(self, context):
        props = context.scene.headshrink_props
        char_name = props.char_name.strip() or 'Char'
        # 1フレームだけ別hashに差し替わるキャラ向け追加hash (role -> [hash8...])。
        # ハードコード禁止: キャラconfig (face_offsets.json の __config__) の
        # extra_hashes を基準に、Mod Export時に同キャラの複数FrameAnalysisから
        # 同サイズ別hashを自動で extra_hash として ini に追加する (下記マージ)。
        cfg = resolve_char_config(face_offsets_path(), char_name)
        extra_hashes = cfg.get('extra_hashes')
        if not isinstance(extra_hashes, dict):
            extra_hashes = {}
        # 出力先は AddonPreferences (userpref.blend 保存・再起動後も復元)
        prefs = context.preferences.addons[__name__].preferences
        output_dir = os.path.join(bpy.path.abspath(prefs.output_dir), char_name)
        coll = bpy.data.collections.get(PREVIEW_COLLECTION)
        if coll is None:
            self.report({'ERROR'}, f"No {PREVIEW_COLLECTION} collection (Preview Setup first)")
            return {'CANCELLED'}
        os.makedirs(output_dir, exist_ok=True)
        cleared = _clean_export_dir(output_dir, char_name)
        mode = 'VB_REPLACE'  # 固定 (VB Replace (Bennett) のみサポート)
        meshes = [o for o in coll.objects
                  if o.type == 'MESH' and o.get('hs_vb0_hash')]
        units = []
        used_names = set()
        primary_for_key: dict = {}  # (role, vert_count) -> primary name (extra化判定用)
        # 同一 (role, vert_count) のセカンダリVB (例: 7a73d3b5 は c9846fd5 と同サイズ) は
        # 別primaryとしてBase/Keyを作らず extra_hash として再分類 (Noelle d265427cと同様)。
        # 同一トポロジなので primary の delta を共有して変形を再現する。
        delta_cache = {}
        for obj in meshes:
            vb0 = obj['hs_vb0_hash']
            mesh = obj.data
            attr = mesh.attributes.get('hs_original_pos')
            if attr is None:
                self.report({'ERROR'}, f"{obj.name}: no hs_original_pos (run Preview Apply first)")
                return {'CANCELLED'}
            vert_count = len(mesh.vertices)
            role = obj.get('hs_role', 'OTHER')
            # 7a73d3b5 冗長排除: 同一 (role, vert_count) の2個目以降は extra へ
            _dup_key = (role, vert_count)
            if role != 'BODY' and _dup_key in primary_for_key:
                lst = extra_hashes.setdefault(role, [])
                if vb0 not in lst and vb0 not in {u['vb_hash'] for u in units}:
                    lst.append(vb0)
                continue
            unit = unit_name_for_role(role, vb0)
            # 同名ユニット (例: MOUTH がプライマリ+セカンダリで2つ) は
            # 3DMigoto が同名セクションを後勝ち上書きして片方の
            # TextureOverride が死ぬため、2 個目以降は vb0 サフィックスで一意化する。
            if unit in used_names:
                unit = f"{unit}_{vb0[:8]}"
            used_names.add(unit)
            name = char_name + unit
            # v.co already carries every preview transform (shrink, shift)
            # because preview_shrink_mesh writes back local coords.
            verts = [display_to_game(tuple(v.co)) for v in mesh.vertices]
            if mode == 'VB_REPLACE' and role == 'BODY':
                # IB分割汎用: 偽Bodyプレビューなら position_vb の正規カウントで
                # BodyPosition.buf を生成 (偽の vb0 は export に使わない)
                is_fake = bool(obj.get('hs_is_fake_body'))
                if not is_fake and _has_ib_split(_dump_cache.get('ib_splits') or {}):
                    # units_map に偽Bodyが登録された場合も generic に検出
                    if _is_fake_body_pair({'vb0': vb0, 'vert_count': vert_count}, _dump_cache):
                        is_fake = True
                position_vb = None
                dump_hash = None
                dump_path = None
                pv_verts = None
                position_hash = None
                if is_fake:
                    # 正規の position_vb (例 28247) を使う
                    real = None
                    rh = obj.get('hs_real_position_vb')
                    if rh:
                        real = (_dump_cache.get('position_vb') or {}).get(rh)
                        if real:
                            real = {'vb_hash': rh, 'path': real['path'], 'vert_count': real['vert_count']}
                    if real is None:
                        real = _find_real_position_vb(_dump_cache.get('position_vb') or {})
                    if real is None:
                        real = _dump_cache.get('real_position_vb')
                    if real is None:
                        self.report({'ERROR'}, f"{name}: IB-split fake Body but real position_vb not found. Re-dump and re-run Analyze Dump.")
                        return {'CANCELLED'}
                    position_vb = real
                    dump_hash = real['vb_hash']
                    dump_path = real['path']
                    # 偽Bodyは正規 position_vb (pre-skin) を既に使っている
                    position_hash = dump_hash
                    # 偽メッシュは 220k 等で大きいため正規カウントでスライス
                    all_pv = [display_to_position_vb(tuple(v.co)) for v in mesh.vertices]
                    rv = real['vert_count']
                    if len(all_pv) >= rv:
                        pv_verts = all_pv[:rv]
                    else:
                        pv_verts = all_pv + [(0.0, 0.0, 0.0)] * (rv - len(all_pv))
                    # unit vert_count は正規のカウントで上書き
                    vert_count = rv
                else:
                    # 通常: pre-skin position buffer (same vertex count)
                    position_vb = find_position_vb(
                        _dump_cache, vb0, vert_count)
                    if position_vb is None:
                        self.report({'ERROR'}, f"{name}: pre-skin position_vb for "
                                               f"{vb0} not found (skinning "
                                               f"vs={props.position_vs}). The dump "
                                               f"lacks the skinning pass vb0; "
                                               f"re-dump and re-run Analyze Dump.")
                        return {'CANCELLED'}
                    dump_hash = position_vb['vb_hash']
                    dump_path = position_vb['path']
                    # SO-only hash (bbdaf598) -> Draw hash (e36be83b) 統一: log.txt Draw 出現で汎用的に
                    drawn_set = _dump_cache.get('drawn_vb0') or set()
                    if dump_hash and drawn_set and dump_hash.lower()[:8] not in drawn_set:
                        # 同 vert_count の Draw可視 hash を dump_dir から探索
                        body_vc = position_vb.get('vert_count')
                        alt = None
                        # まず position_vb 内の drawn エントリ
                        for h2, info2 in (_dump_cache.get('position_vb') or {}).items():
                            if h2.lower()[:8] in drawn_set and info2.get('vert_count') == body_vc and h2.lower()[:8] != dump_hash.lower()[:8]:
                                alt = h2
                                break
                        if not alt:
                            scan_dir = char_dump_dir(char_name) or getattr(prefs, 'dump_dir', '')
                            try:
                                scan_dir = os.path.abspath(scan_dir) if scan_dir else ''
                            except Exception:
                                scan_dir = ''
                            if scan_dir and os.path.isdir(scan_dir):
                                for r2, _, fs2 in os.walk(scan_dir):
                                    for fn2 in fs2:
                                        if not fn2.lower().endswith('.buf'):
                                            continue
                                        m2 = _DUMP_FRAME_RE.match(fn2)
                                        if m2:
                                            hh = m2.group(2).lower()[:8]
                                        elif os.path.basename(r2) == 'deduped':
                                            hh = os.path.splitext(fn2)[0].lower()
                                            if len(hh) != 8:
                                                continue
                                        else:
                                            continue
                                        if hh not in drawn_set:
                                            continue
                                        p2 = os.path.join(r2, fn2)
                                        try:
                                            vc2 = os.path.getsize(p2) // DUMP_STRIDE
                                        except OSError:
                                            continue
                                        if vc2 == body_vc:
                                            alt = hh
                                            break
                                    if alt:
                                        break
                        if alt:
                            dump_hash = alt
                    # IB分割キャラ: Position 置換 hash は pre-skin (SO) バッファ。
                    # drawn hash (post-skin) を置換するとモデルローカル座標で
                    # 上書きしてアニメ停止+体消滅する (実証済み)。BodyGate は
                    # drawn のまま維持するため units には position_hash を別持つ。
                    position_hash = dump_hash
                    if _has_ib_split(_dump_cache.get('ib_splits') or {}):
                        pv = find_position_vb(
                            _dump_cache, vb0, vert_count, drawn_filter=False)
                        if pv:
                            position_hash = pv['vb_hash']
                    pv_verts = [display_to_position_vb(tuple(v.co))
                                for v in mesh.vertices]
                # Bennett-mimic: overwrite only the position float3 of
                # the real pre-skin vb0. normal/tangent stay from the
                # dump; the game VS re-skins the new positions, so the
                # body follows animations exactly.
                with open(dump_path, 'rb') as f:
                    dump_bytes = f.read()
                pos_data = build_position_buf(dump_bytes, pv_verts)
                with open(os.path.join(output_dir, f"{name}Position.buf"),
                          'wb') as f:
                    f.write(pos_data)
                # IB match_first_index split — Draw可視 Body と同フレーム・同vs/psでペアになる IB のみに限定 (泛用)
                ib_hash = None
                ib_splits = None
                try:
                    splits_map = _dump_cache.get('ib_splits') or {}
                    if splits_map and dump_hash:
                        # Body の Draw可視 hash とペアになる IB のみに絞る
                        scan_dir2 = char_dump_dir(char_name) or getattr(prefs, 'dump_dir', '')
                        try:
                            scan_dir2 = os.path.abspath(scan_dir2) if scan_dir2 else ''
                        except Exception:
                            scan_dir2 = ''
                        paired = _find_paired_ibs(scan_dir2, dump_hash) if scan_dir2 else set()
                        # paired が空なら fallback で絞らず(過去キャラ互換)、あるなら絞る
                        cand_map = {k: v for k, v in splits_map.items() if k in paired} if paired else splits_map
                        best = None
                        best_total = -1
                        for kh, sp in cand_map.items():
                            if len(sp) >= 2:
                                tot = sum(c for _, c in sp)
                                if tot > best_total:
                                    best_total = tot
                                    best = (kh, sp)
                        if best:
                            ib_hash, ib_splits = best
                except Exception:
                    pass
                # IB ファイルを R32 で書き出し (INI の Resource と対応)
                if ib_hash and ib_splits:
                    dump_dir_for_ib = getattr(prefs, 'dump_dir', '')
                    try:
                        dump_dir_for_ib = bpy.path.abspath(dump_dir_for_ib) if dump_dir_for_ib else ''
                    except Exception:
                        pass
                    ib_path = _find_ib_path(dump_dir_for_ib, ib_hash) if dump_dir_for_ib else ''
                    if ib_path and os.path.exists(ib_path):
                        try:
                            with open(ib_path, 'rb') as f:
                                ib_data = f.read()
                            for idx2, (first2, cnt2) in enumerate(sorted(ib_splits)[:3]):
                                part2 = ['Head', 'Body', 'Dress'][idx2]
                                res_name2 = f"{char_name}{part2}"
                                s = first2 * DUMP_INDEX_BYTES
                                e = (first2 + cnt2) * DUMP_INDEX_BYTES
                                sl = ib_data[s:e]
                                if sl:
                                    # R16 -> R32
                                    n = len(sl) // DUMP_INDEX_BYTES
                                    try:
                                        indices = struct.unpack(f'<{n}H', sl)
                                        sl = struct.pack(f'<{n}I', *indices)
                                    except Exception:
                                        pass
                                    with open(os.path.join(output_dir, f"{res_name2}.ib"), 'wb') as outf:
                                        outf.write(sl)
                        except Exception:
                            pass
                    units.append({'name': name, 'vb_hash': dump_hash,
                                  'position_hash': position_hash,
                                  'vert_count': vert_count, 'role': 'BODY',
                                  'ib': ib_hash, 'ib_splits': ib_splits})
                else:
                    units.append({'name': name, 'vb_hash': dump_hash,
                                  'position_hash': position_hash,
                                  'vert_count': vert_count, 'role': 'BODY'})
                primary_for_key[('BODY', vert_count)] = name
                continue
            # CopyDispatch path (face units, COPY_DISPATCH mode, or fallback).
            flat = [0.0] * (vert_count * 3)
            attr.data.foreach_get('vector', flat)
            # Base = original (pre-shrink) positions, back to game space so
            # the .buf files match the dump. The HLSL delta shader reads only
            # the position component, so normal/tangent are left zero.
            base_verts = [display_to_game(tuple(flat[i:i + 3]))
                          for i in range(0, len(flat), 3)]
            base_data = replace_positions(bytes(vert_count * DUMP_STRIDE), base_verts, DUMP_STRIDE)
            key = (role, vert_count)
            if key not in delta_cache:
                delta_cache[key] = [(v[0] - b[0], v[1] - b[1], v[2] - b[2])
                                    for b, v in zip(base_verts, verts)]
            # セカンダリ (同一 role/vert_count の2個目以降) はプライマリの
            # delta を base に加算して key を再現する。verts は配置差で
            # ズレた preview 結果なので使わない。
            delta = delta_cache[key]
            key_verts = [(b[0] + d[0], b[1] + d[1], b[2] + d[2])
                         for b, d in zip(base_verts, delta)]
            key_data = replace_positions(base_data, key_verts, DUMP_STRIDE)
            with open(os.path.join(output_dir, f"{name}Base.buf"), 'wb') as f:
                f.write(base_data)
            with open(os.path.join(output_dir, f"{name}Key.buf"), 'wb') as f:
                f.write(key_data)
            units.append({'name': name, 'vb_hash': vb0, 'vert_count': vert_count,
                          'role': role})
            primary_for_key[(role, vert_count)] = name
        if not units:
            self.report({'ERROR'}, "No hs_vb0_hash meshes in HS_Preview")
            return {'CANCELLED'}
        # Mod Export時に同キャラの複数FrameAnalysisから同サイズ別hashを自動で
        # extra_hashとしてiniに追加 (assets/Dump/<Char> 走査、無ければ dump_dir
        # フォールバック)。手動 (face_offsets.json の extra_hashes) が優先:
        # 自動検出は手動に無い hash のみ追加する (重複はスキップ)。
        auto = auto_extra_hashes(
            char_name, units, dump_dir=getattr(prefs, 'dump_dir', ''))
        for role, hashes in auto.items():
            merged = extra_hashes.setdefault(role, [])
            for h in hashes:
                if h not in merged:
                    merged.append(h)
        # Bodyハッシュ優先ゲート (キャラ固有, 共有皮膚テクスチャ d4841e1a 等の波及を防ぐ)
        # units内 BODY の vb_hash (= position_vb hash, 例 Yanfei eb8b62d3) を $is トリガーに使用
        # Drawフィルター: SO-only hash (bbdaf598) は除外し Draw可視 hash (e36be83b) を優先
        # 無ければ faceDiffuse にフォールバック、どちらも無ければゲート無し
        body_hash = next((u['vb_hash'] for u in units if u.get('role') == 'BODY'), None)
        drawn_for_gate = _dump_cache.get('drawn_vb0') or set()
        if body_hash and drawn_for_gate and body_hash.lower()[:8] not in drawn_for_gate:
            body_vc = next((u['vert_count'] for u in units if u.get('role') == 'BODY'), None)
            if body_vc:
                # scan for a drawn vb0 with same vert_count (e.g. Mizuki e36be83b 22226)
                alt = None
                scan_dir = char_dump_dir(char_name) or getattr(prefs, 'dump_dir', '')
                if scan_dir:
                    try:
                        scan_dir = os.path.abspath(scan_dir) if hasattr(scan_dir, 'lower') else str(scan_dir)
                    except Exception:
                        pass
                    if os.path.isdir(scan_dir):
                        for root2, _, files2 in os.walk(scan_dir):
                            for fn2 in files2:
                                if not fn2.lower().endswith('.buf'):
                                    continue
                                m2 = _DUMP_FRAME_RE.match(fn2)
                                if m2:
                                    hh = m2.group(2).lower()[:8]
                                elif os.path.basename(root2) == 'deduped':
                                    hh = os.path.splitext(fn2)[0].lower()
                                    if not hh or len(hh) != 8:
                                        continue
                                else:
                                    continue
                                if hh not in drawn_for_gate:
                                    continue
                                p2 = os.path.join(root2, fn2)
                                try:
                                    vc2 = os.path.getsize(p2) // DUMP_STRIDE
                                except OSError:
                                    continue
                                if vc2 == body_vc:
                                    alt = hh
                                    break
                            if alt:
                                break
                if alt:
                    body_hash = alt
        face_diffuse_hash = None
        if not body_hash:
            face_vb_hashes = [u['vb_hash'] for u in units if u.get('role') != 'BODY']
            face_diffuse_hash = _find_face_diffuse_hash(char_name, face_vb_hashes)
        # IB split overrides — Draw可視 Body とペアになる IB のみに限定 (泛用、他小物は出さない)
        ib_splits_for_ini = None
        raw_splits = _dump_cache.get('ib_splits') or {}
        if _has_ib_split(raw_splits) and body_hash:
            scan_dir3 = char_dump_dir(char_name) or getattr(prefs, 'dump_dir', '')
            try:
                scan_dir3 = os.path.abspath(scan_dir3) if scan_dir3 else ''
            except Exception:
                scan_dir3 = ''
            paired3 = _find_paired_ibs(scan_dir3, body_hash) if scan_dir3 else set()
            if paired3:
                filtered = {k: v for k, v in raw_splits.items() if k in paired3}
                if filtered and any(len(v) >= 2 for v in filtered.values()):
                    ib_splits_for_ini = filtered
            else:
                # fallback: when pairing fails (old dump without vs/ps), pass nothing to avoid 12重複爆殖
                ib_splits_for_ini = None
        elif _has_ib_split(raw_splits) and not body_hash:
            # Body無しキャラでは外部IBは出さない(重複防止)
            ib_splits_for_ini = None
        with open(os.path.join(output_dir, f"{char_name}Head.hlsl"), 'w', newline='\n') as f:
            f.write(DIFF_HLSL)
        with open(os.path.join(output_dir, f"{char_name}.ini"), 'w', newline='\n') as f:
            f.write(build_diff_ini(char_name, units, mode, extra_hashes, None, face_diffuse_hash, body_hash, ib_splits_for_ini))
        self.report({'INFO'}, f"Diff mod exported to {output_dir} "
                              f"({len(units)} unit(s): "
                              f"{', '.join(u['name'] for u in units)})"
                              f"{'; cleared ' + str(cleared) + ' stale file(s)' if cleared else ''}")
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


class NHS_PT_Panel(bpy.types.Panel):
    bl_label = "HeadShrink"
    bl_idname = "NHS_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HeadShrink"

    def draw(self, context):
        layout = self.layout
        props = context.scene.headshrink_props
        prefs = context.preferences.addons[__name__].preferences

        # ---- Step 1: ダンプディレクトリ ----
        box = layout.box()
        box.label(text="① ダンプディレクトリ", icon='FILE_FOLDER')
        box.prop(prefs, "dump_dir")

        # ---- Step 2: キャラメッシュ登録 (Units) ----
        box = layout.box()
        box.label(text="② キャラメッシュ登録 (Units)", icon='GROUP')
        box.prop(props, "char_name")
        box.operator("headshrink.analyze_dump", icon='FILE_REFRESH')
        box.template_list("HS_UL_DumpPairList", "dump_pairs", props,
                          "dump_pairs", props, "dump_pairs_index", rows=6)
        box.operator("headshrink.preview_pair", icon='RESTRICT_VIEW_OFF',
                     text="選択ペアを表示")
        row = box.row()
        row.prop(props, "units_role", text="")
        row.operator("headshrink.units_add_pair", icon='ADD',
                     text="表示中のペアを登録")
        row = box.row(align=True)
        row.prop(props, "units_vb0", text="VB")
        row.prop(props, "units_role", text="")
        box.operator("headshrink.units_add", icon='ADD')
        box.template_list("HS_UL_UnitsList", "units_list", props,
                          "units_list", props, "units_list_index", rows=3)
        row = box.row()
        row.operator("headshrink.units_remove", icon='X')

        # ---- Step 3: セットアップ ----
        box = layout.box()
        box.label(text="③ セットアップ", icon='PLAY')
        box.operator("headshrink.auto_setup", icon='PLAY')

        # ---- Step 4: 頭部調整 (プレビュー) ----
        box = layout.box()
        box.label(text="④ 頭部調整 (プレビュー)", icon='VIEWZOOM')
        box.prop(props, "face_snap_enabled")
        box.operator("headshrink.reposition_faces", icon='SNAP_FACE')
        box.operator("headshrink.preview_reset", icon='LOOP_BACK')
        row = box.row()
        row.operator("headshrink.save_face_offsets", text="Save Char", icon='FILE_TICK')
        row.operator("headshrink.load_char_config", text="Load Char", icon='FILE_REFRESH')
        row = box.row()
        row.operator("headshrink.save_default_config", text="Save Default", icon='FILE_TICK')
        row.operator("headshrink.load_default_config", text="Load Default", icon='FILE_REFRESH')
        box.label(text="── Shrink ──", icon='DOWNARROW_HLT')
        box.prop(props, "shrink_center")
        box.prop(props, "shrink_half")
        box.prop(props, "shrink_scale")
        box.prop(props, "shrink_falloff")
        box.prop(props, "shrink_shift")
        box.label(text="── Face Offset ──", icon='DOWNARROW_HLT')
        box.prop(props, "face_offset_eye")
        box.prop(props, "face_offset_mouth")
        box.prop(props, "face_offset_brow")

        # ---- Step 5: mod 生成 (出力) ----
        box = layout.box()
        box.label(text="⑤ mod 生成 (出力)", icon='EXPORT')
        box.prop(prefs, "output_dir")
        box.operator("headshrink.export_diff", icon='EXPORT')


# ===== REGISTRATION =====
classes = (
    NHSUnitItem,
    NHSDumpPairItem,
    HS_UL_UnitsList,
    HS_UL_DumpPairList,
    NHSAddonPreferences,
    NHSProps,
    NHS_OT_AnalyzeDump,
    NHS_OT_UnitsAdd,
    NHS_OT_UnitsAddPair,
    NHS_OT_UnitsRemove,
    NHS_OT_ImportDump,
    NHS_OT_ImportAll,
    NHS_OT_AutoSetup,
    NHS_OT_PreviewPair,
    NHS_OT_PreviewSetup,
    NHS_OT_PreviewApply,
    NHS_OT_RepositionFaces,
    NHS_OT_PreviewReset,
    NHS_OT_SaveFaceOffsets,
    NHS_OT_SaveDefaultConfig,
    NHS_OT_LoadCharConfig,
    NHS_OT_LoadDefaultConfig,
    NHS_OT_ExportDiff,
    NHS_OT_SetRole,
    NHS_PT_Panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.headshrink_props = bpy.props.PointerProperty(type=NHSProps)
    # config.json __global__ から dump_dir / output_dir を復元（なんでもあり設定ファイル化）
    try:
        dump_dir, output_dir = load_global_dirs()
        if (dump_dir or output_dir) and bpy.context.preferences is not None:
            try:
                prefs = bpy.context.preferences.addons[__name__].preferences
                if dump_dir and hasattr(prefs, "dump_dir"):
                    # AddonPreferences の初期値と違えば上書き
                    if prefs.dump_dir != dump_dir:
                        prefs.dump_dir = dump_dir
                if output_dir and hasattr(prefs, "output_dir"):
                    if prefs.output_dir != output_dir:
                        prefs.output_dir = output_dir
            except Exception:
                pass
    except Exception:
        pass


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.headshrink_props


if __name__ == "__main__":
    register()
