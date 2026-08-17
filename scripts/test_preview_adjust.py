"""Unit tests for the whole-body preview + CopyDispatch diff helpers.

Covers: shrink box membership (inside/outside/boundary), shrink_positions
(scale about center, outside unchanged, scale=1.0 identity), replace_positions
(pos-only overwrite keeps normal/tangent bytes), unit_name_for_hash mapping,
and build_diff_ini structure.

Run: python test_preview_adjust.py
"""
import os
import struct
import sys
import tempfile
import types
import unittest

import numpy as np  # noqa: E402 (境界マッチングテスト用)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# --- minimal bpy stub: only needed for class definitions to import ---
if 'bpy' not in sys.modules:
    bpy_stub = types.ModuleType('bpy')

    def _prop_fn(*args, **kwargs):
        return None

    class _Base:
        pass

    props = types.SimpleNamespace(
        StringProperty=_prop_fn, FloatVectorProperty=_prop_fn,
        EnumProperty=_prop_fn, PointerProperty=_prop_fn,
        CollectionProperty=_prop_fn, PropertyGroup=_Base,
        FloatProperty=_prop_fn, BoolProperty=_prop_fn,
        IntProperty=_prop_fn,
    )

    bpy_stub.props = props
    bpy_stub.types = types.SimpleNamespace(
        PropertyGroup=_Base, Operator=_Base, Panel=_Base, UIList=_Base)
    bpy_stub.utils = types.SimpleNamespace(
        register_class=lambda c: None, unregister_class=lambda c: None)
    bpy_stub.path = types.SimpleNamespace(abspath=lambda p: p)
    bpy_stub.data = types.SimpleNamespace()
    bpy_stub.context = types.SimpleNamespace()
    sys.modules['bpy'] = bpy_stub

import headshrink_addon as hs  # noqa: E402

CENTER = (-0.3, 0.0, 0.0)
HALF = (0.5, 0.25, 0.35)


def make_vb(n, stride=40):
    """n verts: xyz=(v, 2v, 3v) as float32, normal=(1,0,0), tangent zeroed."""
    out = bytearray()
    for v in range(n):
        out += struct.pack('<3f', float(v), float(v * 2), float(v * 3))
        out += struct.pack('<3f', 1.0, 0.0, 0.0)   # normal
        out += b'\x00' * (stride - 24)             # tangent + rest
    return bytes(out)


class _FakeAttrData:
    def __init__(self, flat):
        self._flat = list(flat)

    def foreach_get(self, name, dest):
        dest[:] = self._flat

    def __getitem__(self, i):
        # data[0].vector 形式 (hs_original_loc の読み出し用)
        return types.SimpleNamespace(
            vector=tuple(self._flat[i * 3:(i + 1) * 3]))


class _FakeAttr:
    def __init__(self, flat):
        self.data = _FakeAttrData(flat)


class _FakeAttributes:
    def __init__(self, attrs):
        self._attrs = attrs

    def get(self, name):
        return self._attrs.get(name)


class _FakeMesh:
    """Minimal mesh stub: hs_original_pos attribute + vertices with .co."""

    def __init__(self, verts, loc=None):
        flat = []
        for v in verts:
            flat.extend(v)
        self.vertices = [types.SimpleNamespace(co=[float(c) for c in v])
                         for v in verts]
        attrs = {'hs_original_pos': _FakeAttr(flat)}
        if loc is not None:
            attrs['hs_original_loc'] = _FakeAttr(list(loc) * len(verts))
        self.attributes = _FakeAttributes(attrs)

    def update(self):
        pass


class PreviewResetTest(unittest.TestCase):
    """NHS_OT_PreviewReset: 頂点 + 配置位置 (hs_original_loc) の復元。"""

    def _run(self, objects):
        hs.bpy.data.collections = types.SimpleNamespace(
            get=lambda name: (types.SimpleNamespace(objects=objects)
                              if name == 'HS_Preview' else None))
        op = hs.NHS_OT_PreviewReset()
        reports = []
        op.report = lambda level, msg: reports.append((set(level), msg))
        result = op.execute(None)
        return result, reports

    def test_reset_restores_verts_and_location(self):
        # G キーで動かした配置位置もセットアップ直後に戻る
        obj = types.SimpleNamespace(
            type='MESH',
            data=_FakeMesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
                           loc=(0.5, 0.0, 0.0)),
            location=[9.0, 9.0, 9.0],
        )
        obj.data.vertices[0].co = [5.0, 5.0, 5.0]
        result, reports = self._run([obj])
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(obj.location, (0.5, 0.0, 0.0))
        self.assertEqual(obj.data.vertices[0].co, [0.0, 0.0, 0.0])
        self.assertEqual(reports[0][1],
                         "Preview reset (verts + location) on 1 mesh(es)")

    def test_reset_without_loc_keeps_location(self):
        # hs_original_loc が無いオブジェクトは位置を触らない (後方互換)
        obj = types.SimpleNamespace(
            type='MESH',
            data=_FakeMesh([(0.0, 0.0, 0.0)]),
            location=[3.0, 4.0, 5.0],
        )
        result, reports = self._run([obj])
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(obj.location, [3.0, 4.0, 5.0])
        self.assertEqual(reports[0][1],
                         "Preview reset (verts + location) on 1 mesh(es)")

    def test_reset_no_collection_rejected(self):
        hs.bpy.data.collections = types.SimpleNamespace(get=lambda name: None)
        op = hs.NHS_OT_PreviewReset()
        reports = []
        op.report = lambda level, msg: reports.append((set(level), msg))
        result = op.execute(None)
        self.assertEqual(result, {'CANCELLED'})
        self.assertIn('ERROR', reports[0][0])


class InShrinkBoxTest(unittest.TestCase):
    def test_inside(self):
        self.assertTrue(hs.in_shrink_box((0.0, 0.0, 0.0), CENTER, HALF))

    def test_outside_axis(self):
        self.assertFalse(hs.in_shrink_box((1.0, 0.0, 0.0), CENTER, HALF))
        self.assertFalse(hs.in_shrink_box((-1.0, 0.0, 0.0), CENTER, HALF))

    def test_boundary_inclusive(self):
        # exactly half* (|p-c| == half) is inside (<=)
        self.assertTrue(hs.in_shrink_box((CENTER[0] + HALF[0], 0.0, 0.0), CENTER, HALF))
        self.assertTrue(hs.in_shrink_box((CENTER[0] - HALF[0], 0.0, 0.0), CENTER, HALF))
        self.assertTrue(hs.in_shrink_box((0.0, HALF[1], 0.0), CENTER, HALF))


class ShrinkPositionsTest(unittest.TestCase):
    def test_in_box_scales_about_center(self):
        p = (0.0, 0.0, 0.0)
        out = hs.shrink_positions([p], CENTER, HALF, 0.5)[0]
        self.assertAlmostEqual(out[0], CENTER[0] * 0.5)  # (-0.3+0.3*0.5)=-0.15
        self.assertAlmostEqual(out[1], 0.0)
        self.assertAlmostEqual(out[2], 0.0)

    def test_outside_unchanged(self):
        p = (5.0, -3.0, 2.0)
        self.assertEqual(hs.shrink_positions([p], CENTER, HALF, 0.5), [p])

    def test_scale_one_is_identity(self):
        verts = [(0.0, 0.1, -0.2), (1.0, 2.0, 3.0), (-0.3, 0.25, 0.35)]
        out = hs.shrink_positions(verts, CENTER, HALF, 1.0)
        for a, b in zip(verts, out):
            for x, y in zip(a, b):
                self.assertAlmostEqual(x, y)

    def test_mixed_keeps_order(self):
        verts = [(0.0, 0.0, 0.0), (9.0, 9.0, 9.0), (0.1, 0.1, 0.1)]
        out = hs.shrink_positions(verts, CENTER, HALF, 0.9)
        self.assertEqual(len(out), 3)
        self.assertEqual(out[1], (9.0, 9.0, 9.0))  # outside untouched


class ShrinkFalloffTest(unittest.TestCase):
    def test_falloff_zero_legacy_behavior(self):
        # in-box scaled, outside untouched (same as default arg)
        verts = [(0.0, 0.0, 0.0), (5.0, -3.0, 2.0)]
        out = hs.shrink_positions(verts, CENTER, HALF, 0.5, falloff=0.0)
        self.assertAlmostEqual(out[0][0], CENTER[0] * 0.5)
        self.assertEqual(out[1], verts[1])

    def test_in_box_full_scale(self):
        # inside the box the fade has no effect: exact scale factor
        p = (0.0, 0.0, 0.0)  # d=0
        out = hs.shrink_positions([p], CENTER, HALF, 0.5, falloff=0.3)[0]
        self.assertAlmostEqual(out[0], CENTER[0] * 0.5)
        self.assertAlmostEqual(out[1], 0.0)
        self.assertAlmostEqual(out[2], 0.0)

    def test_boundary_full_scale(self):
        # on the box surface (d=1.0) the factor is still 'scale'
        p = (CENTER[0] + HALF[0], 0.0, 0.0)
        out = hs.shrink_positions([p], CENTER, HALF, 0.5, falloff=0.3)[0]
        self.assertAlmostEqual(out[0],
                               CENTER[0] + HALF[0] * 0.5)

    def test_fade_band_interpolates(self):
        # d = 1.5 with falloff=1.0 -> t=0.5, s = 0.5 + 0.5*0.5 = 0.75
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (1.5, 0.0, 0.0)
        out = hs.shrink_positions([p], center, half, 0.5, falloff=1.0)[0]
        self.assertAlmostEqual(out[0], 1.5 * 0.75)
        self.assertAlmostEqual(out[1], 0.0)
        self.assertAlmostEqual(out[2], 0.0)

    def test_mid_fade_less_shrunk_than_inside(self):
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        inside = hs.shrink_positions([(0.5, 0.0, 0.0)], center, half,
                                     0.5, falloff=1.0)[0][0]
        mid = hs.shrink_positions([(1.5, 0.0, 0.0)], center, half,
                                  0.5, falloff=1.0)[0][0]
        self.assertAlmostEqual(inside, 0.5 * 0.5)
        self.assertAlmostEqual(mid, 1.5 * 0.75)
        self.assertGreater(mid, inside)  # fade vertex stays closer to origin

    def test_outside_band_unchanged(self):
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (3.0, 0.0, 0.0)  # d=3 > 1+0.5
        out = hs.shrink_positions([p], center, half, 0.5, falloff=0.5)
        self.assertEqual(out, [p])

    def test_boundary_continuity_at_band_end(self):
        # d == 1.0 + falloff -> t=1.0 -> s=1.0 -> vertex unchanged
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (1.5, 0.0, 0.0)  # d=1.5 == 1+0.5
        out = hs.shrink_positions([p], center, half, 0.5, falloff=0.5)
        self.assertEqual(out, [p])

    def test_half_zero_axis_no_crash(self):
        # half (1,0,1): y axis excluded from distance -> d from x only
        center = (0.0, 0.0, 0.0)
        half = (1.0, 0.0, 1.0)
        p_in = (0.5, 10.0, 0.0)   # x inside -> scaled (y too: scale applies to all axes)
        p_out = (2.0, 10.0, 0.0)  # x outside band -> unchanged
        out = hs.shrink_positions([p_in, p_out], center, half, 0.5,
                                  falloff=0.5)
        self.assertAlmostEqual(out[0][0], 0.5 * 0.5)
        self.assertAlmostEqual(out[0][1], 10.0 * 0.5)  # scaled about center
        self.assertEqual(out[1], p_out)

    def test_all_zero_half_collapsed_box(self):
        # degenerate: everything stays in place (no division by zero)
        center = (1.0, 2.0, 3.0)
        half = (0.0, 0.0, 0.0)
        verts = [(0.0, 0.0, 0.0), (5.0, 5.0, 5.0)]
        self.assertEqual(hs.shrink_positions(verts, center, half, 0.5,
                                             falloff=0.5), verts)


class OriginSeparationTest(unittest.TestCase):
    """shrink_origin decouples the scale pivot from the box position."""

    def test_origin_separates_scale_pivot(self):
        # box at (0,0,0), pivot at (0,0,1): in-box vertex scales about origin,
        # so a vertex at the origin moves halfway toward the pivot at scale 0.5
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        origin = (0.0, 0.0, 1.0)
        out = hs.shrink_positions([(0.0, 0.0, 0.0)], center, half, 0.5,
                                  origin=origin)[0]
        self.assertAlmostEqual(out[2], 0.5)   # origin + (p-origin)*0.5
        self.assertAlmostEqual(out[0], 0.0)
        self.assertAlmostEqual(out[1], 0.0)

    def test_origin_none_uses_center(self):
        # backward compatibility: default keeps legacy center-based scaling
        p = (0.0, 0.0, 0.0)
        center = (-0.3, 0.0, 0.0)
        half = (0.5, 0.25, 0.35)
        out = hs.shrink_positions([p], center, half, 0.5)[0]
        self.assertAlmostEqual(out[0], center[0] * 0.5)
        self.assertAlmostEqual(out[1], 0.0)
        self.assertAlmostEqual(out[2], 0.0)

    def test_box_test_still_center(self):
        # membership is judged against center; origin far away must not
        # pull out-of-box vertices in or drop in-box ones
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        origin = (10.0, 0.0, 0.0)
        verts = [(0.5, 0.0, 0.0), (5.0, 0.0, 0.0)]  # in-box / out-of-box
        out = hs.shrink_positions(verts, center, half, 0.5, origin=origin)
        self.assertNotEqual(out[0], verts[0])      # in-box: transformed
        self.assertEqual(out[1], verts[1])         # out-of-box: untouched

    def test_all_verts_uses_origin(self):
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        origin = (0.0, 0.0, 1.0)
        out = hs.shrink_positions([(0.0, 0.0, 0.0)], center, half, 0.5,
                                  all_verts=True, origin=origin)[0]
        self.assertAlmostEqual(out[2], 0.5)        # uniform mode also pivots on origin

    def test_neck_pivot_stays_put(self):
        # user scenario: box high on the head, pivot at the neck (z=0.03).
        # A vertex exactly at the pivot must not move when scaled.
        center = (0.0, 0.0, 0.48)
        half = (0.5, 0.25, 0.35)
        origin = (0.0, 0.0, 0.03)
        p = (0.0, 0.0, 0.03)  # at the pivot, inside the box (|0.03-0.48|<=0.35)
        out = hs.shrink_positions([p], center, half, 0.9, origin=origin)[0]
        for x, y in zip(out, p):
            self.assertAlmostEqual(x, y)


class ReplacePositionsTest(unittest.TestCase):
    def test_pos_only_overwritten(self):
        data = make_vb(3)
        new_verts = [(10.0, 20.0, 30.0), (40.0, 50.0, 60.0), (70.0, 80.0, 90.0)]
        out = hs.replace_positions(data, new_verts, 40)
        self.assertEqual(len(out), len(data))
        for v in range(3):
            x, y, z = struct.unpack_from('<3f', out, v * 40)
            self.assertEqual((x, y, z), new_verts[v])
            # normal bytes preserved
            nx, ny, nz = struct.unpack_from('<3f', out, v * 40 + 12)
            self.assertEqual((nx, ny, nz), (1.0, 0.0, 0.0))
        # tail bytes (tangent/rest) of vertex 0 preserved
        self.assertEqual(out[24:40], data[24:40])

    def test_stride_respected(self):
        data = make_vb(2, stride=40)
        out = hs.replace_positions(data, [(1.0, 1.0, 1.0), (2.0, 2.0, 2.0)], 40)
        self.assertEqual(len(out), 80)

    def test_zero_base_pos_only(self):
        # export_diff builds Base over a zero buffer (hs_original_pos only):
        # positions written, normal/tangent stay zero.
        n = 2
        base = bytes(n * 40)
        verts = [(1.0, 2.0, 3.0), (-1.0, -2.0, -3.0)]
        out = hs.replace_positions(base, verts, 40)
        for v in range(n):
            self.assertEqual(struct.unpack_from('<3f', out, v * 40), verts[v])
            self.assertEqual(struct.unpack_from('<3f', out, v * 40 + 12),
                             (0.0, 0.0, 0.0))
            self.assertEqual(out[v * 40 + 24:v * 40 + 40], b'\x00' * 16)


class CoordTransformTest(unittest.TestCase):
    def test_roundtrip_inverse(self):
        pts = [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0), (-0.5, 0.25, -0.9),
               (1.2, -3.4, 5.6), (0.0, 1.0, 0.0)]
        for p in pts:
            self.assertEqual(hs.display_to_game(hs.game_to_display(p)), p)

    def test_known_axis_mapping(self):
        # game x+ = down -> display z- (up direction is display z+)
        self.assertEqual(hs.game_to_display((1.0, 0.0, 0.0)), (0.0, 0.0, -1.0))
        self.assertEqual(hs.game_to_display((0.0, 1.0, 0.0)), (0.0, 1.0, 0.0))
        self.assertEqual(hs.game_to_display((0.0, 0.0, 1.0)), (1.0, 0.0, 0.0))
        self.assertEqual(hs.display_to_game((0.0, 0.0, -1.0)), (1.0, 0.0, 0.0))
        self.assertEqual(hs.display_to_game((1.0, 0.0, 0.0)), (0.0, 0.0, 1.0))

    def test_export_roundtrip_matches_dump(self):
        # export path: dump (game) -> load_dump_mesh (display) -> hs_original_pos
        # -> display_to_game -> .buf pos == original dump pos
        game = (1.0, 2.0, 3.0)
        display = hs.game_to_display(game)
        self.assertEqual(hs.display_to_game(display), game)


class LoadDumpMeshTransformTest(unittest.TestCase):
    def _write_dump(self, game_verts, ib):
        with tempfile.TemporaryDirectory() as d:
            vb_path = os.path.join(d, 'vb0.buf')
            ib_path = os.path.join(d, 'ib.buf')
            vb = bytearray()
            for p in game_verts:
                vb += struct.pack('<3f', *p)
                vb += b'\x00' * (40 - 12)
            with open(vb_path, 'wb') as f:
                f.write(vb)
            with open(ib_path, 'wb') as f:
                f.write(ib)
            return hs.load_dump_mesh(vb_path, ib_path)

    def test_verts_in_display_coords(self):
        # game (x=1,y=2,z=3) -> display (3,2,-1)
        verts, faces, _ = self._write_dump(
            [(1.0, 2.0, 3.0), (0.0, 0.0, 0.0)], struct.pack('<3H', 0, 0, 0))
        self.assertEqual(verts[0], (3.0, 2.0, -1.0))
        self.assertEqual(verts[1], (0.0, 0.0, 0.0))
        self.assertEqual(faces, [(0, 0, 0)])


class HeadCenterTest(unittest.TestCase):
    def test_top_fraction_center(self):
        # z in 0..3; top 25% = z >= 2 -> verts (2,2,2) and (3,3,3)
        verts = [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0),
                 (2.0, 2.0, 2.0), (3.0, 3.0, 3.0)]
        self.assertEqual(hs.head_center_from_verts(verts, 0.25),
                         (2.5, 2.5, 2.5))

    def test_flat_z_selects_all(self):
        verts = [(0.0, 0.0, 1.0), (2.0, 0.0, 1.0),
                 (0.0, 4.0, 1.0), (2.0, 4.0, 1.0)]
        self.assertEqual(hs.head_center_from_verts(verts, 0.25),
                         (1.0, 2.0, 1.0))

    def test_empty(self):
        self.assertIsNone(hs.head_center_from_verts([], 0.25))

    def test_axis_bias(self):
        # all top z -> higher x/y dominate only if z varies; here z equal
        verts = [(0.0, 0.0, 0.5), (10.0, 0.0, 0.5)]
        self.assertEqual(hs.head_center_from_verts(verts, 0.25),
                         (5.0, 0.0, 0.5))


class RoleNameTest(unittest.TestCase):
    """unit_name_for_role maps a unit role to the diff unit name."""

    def test_known_roles(self):
        self.assertEqual(hs.unit_name_for_role('BODY', 'def7af36'), 'Body')
        self.assertEqual(hs.unit_name_for_role('EYES', '63f702ce'), 'Eyes')
        self.assertEqual(hs.unit_name_for_role('MOUTH', '6192fe1c'), 'Mouth')
        self.assertEqual(hs.unit_name_for_role('BROW', 'ddf54429'), 'Brow')

    def test_other_falls_back_to_hash(self):
        self.assertEqual(hs.unit_name_for_role('OTHER', 'aabbccdd'),
                         'Unit' + 'aabbccdd'[:8])

    def test_empty_role_falls_back_to_hash(self):
        self.assertEqual(hs.unit_name_for_role('', 'aabbccdd'),
                         'Unit' + 'aabbccdd'[:8])


class RoleForPairTest(unittest.TestCase):
    """role_for_pair resolves hs_role from char config, then size heuristics."""

    def test_units_map_takes_priority(self):
        units = {'63f702ce': 'EYES', '6192fe1c': 'MOUTH'}
        self.assertEqual(hs.role_for_pair('63f702ce', 1083, units, False), 'EYES')
        self.assertEqual(hs.role_for_pair('6192fe1c', 877, units, False), 'MOUTH')

    def test_largest_is_head_without_map(self):
        self.assertEqual(hs.role_for_pair('def7af36', 15965, {}, True), 'BODY')

    def test_other_without_map(self):
        self.assertEqual(hs.role_for_pair('aabbccdd', 500, {}, False), 'OTHER')

    def test_unknown_in_map_ignored(self):
        self.assertEqual(hs.role_for_pair('aabbccdd', 500, {'63f702ce': 'EYES'}, False),
                         'OTHER')


class BuildDiffIniTest(unittest.TestCase):
    def test_structure(self):
        ini = hs.build_diff_ini('Noelle', [
            {'name': 'NoelleHead', 'vb_hash': 'def7af36', 'vert_count': 15965},
            {'name': 'NoelleEyes', 'vb_hash': '63f702ce', 'vert_count': 1083},
        ])
        for needle in [
            '[Constants]', 'global $active = 0',
            '[Present]', 'post $active = 0',
            '[TextureOverrideNoelleHead]', 'hash = def7af36', '$active = 1',
            'run = CommandListNoelleHead',
            '[CommandListNoelleHead]',
            'ResourceNoelleHeadDif = copy this',
            'run = CustomShaderNoelleHead',
            'this = ResourceNoelleHeadDif',
            '[ResourceNoelleHeadBase]', 'type = RWBuffer', 'stride = 40',
            'filename = NoelleHeadBase.buf',
            '[ResourceNoelleHeadKey]', 'filename = NoelleHeadKey.buf',
            '[CustomShaderNoelleHead]', 'cs = NoelleHead.hlsl',
            'cs-u1 = copy ResourceNoelleHeadDif',
            'cs-t0 = copy ResourceNoelleHeadBase',
            'cs-t1 = copy ResourceNoelleHeadKey',
            'Dispatch = 15965, 1, 1',
            'ResourceNoelleHeadDif = copy cs-u1', 'post cs-u1 = null',
            '[TextureOverrideNoelleEyes]', 'hash = 63f702ce',
            'Dispatch = 1083, 1, 1',
        ]:
            self.assertIn(needle, ini)
        # header ([Constants]+[Present] active reset) before units
        self.assertLess(ini.rindex('[Present]'),
                        ini.index('[TextureOverrideNoelleHead]'))
        # units in order
        self.assertLess(ini.index('[TextureOverrideNoelleHead]'),
                        ini.index('[TextureOverrideNoelleEyes]'))


class BuildDiffIniModeTest(unittest.TestCase):
    """build_diff_ini mode='VB_REPLACE' (Bennett-mimic): BODY role -> vb0
    buffer override only; face roles / no-role / COPY_DISPATCH keep the
    legacy CopyDispatch structure."""

    def test_vb_replace_body_uses_buffer_override(self):
        ini = hs.build_diff_ini('Noelle', [
            {'name': 'NoelleBody', 'vb_hash': 'def7af36', 'vert_count': 15965,
             'role': 'BODY'},
        ])
        for needle in [
            '[TextureOverrideNoelleBody]',
            'hash = def7af36',
            'vb0 = ResourceNoelleBodyPosition',
            '$active = 1',
            '[ResourceNoelleBodyPosition]',
            'type = Buffer',
            'stride = 40',
            'filename = NoelleBodyPosition.buf',
        ]:
            self.assertIn(needle, ini)
        for banned in ['CommandListNoelleBody', 'CustomShaderNoelleBody',
                       'Base.buf', 'Key.buf', 'cs-u1', 'Dispatch =']:
            self.assertNotIn(banned, ini)

    def test_vb_replace_face_keeps_copydispatch(self):
        ini = hs.build_diff_ini('Noelle', [
            {'name': 'NoelleEyes', 'vb_hash': '63f702ce', 'vert_count': 1083,
             'role': 'EYES'},
        ])
        self.assertIn('run = CommandListNoelleEyes', ini)
        self.assertIn('run = CustomShaderNoelleEyes', ini)
        self.assertNotIn('Position.buf', ini)

    def test_vb_replace_mixed_body_and_face(self):
        ini = hs.build_diff_ini('Noelle', [
            {'name': 'NoelleBody', 'vb_hash': 'def7af36', 'vert_count': 15965,
             'role': 'BODY'},
            {'name': 'NoelleEyes', 'vb_hash': '63f702ce', 'vert_count': 1083,
             'role': 'EYES'},
        ])
        self.assertIn('vb0 = ResourceNoelleBodyPosition', ini)
        self.assertIn('run = CommandListNoelleEyes', ini)
        self.assertLess(ini.index('[TextureOverrideNoelleBody]'),
                        ini.index('[TextureOverrideNoelleEyes]'))

    def test_copydispatch_mode_ignores_role(self):
        ini = hs.build_diff_ini('Noelle', [
            {'name': 'NoelleBody', 'vb_hash': 'def7af36', 'vert_count': 15965,
             'role': 'BODY'},
        ], mode='COPY_DISPATCH')
        self.assertIn('run = CommandListNoelleBody', ini)
        self.assertNotIn('Position.buf', ini)

    def test_no_role_defaults_to_copydispatch(self):
        # role キー無し (既存呼び出し) はデフォルトモードでも CopyDispatch
        ini = hs.build_diff_ini('Noelle', [
            {'name': 'NoelleHead', 'vb_hash': 'def7af36', 'vert_count': 15965},
        ])
        self.assertIn('run = CommandListNoelleHead', ini)


class PositionBufTest(unittest.TestCase):
    """Position.buf helper: dump vb0 bytes with position float3 replaced,
    normal/tangent bytes kept; dump vb0 path lookup."""

    def test_build_position_buf_replaces_pos_keeps_rest(self):
        n = 3
        dump = bytearray()
        for v in range(n):
            dump += struct.pack('<3f', float(v), 0.0, 0.0)  # position
            dump += struct.pack('<3f', 0.5, 0.5, 0.5)       # normal (keep)
            dump += b'\xAA' * (40 - 24)                     # tangent + rest
        new_pos = [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0)]
        out = hs.build_position_buf(bytes(dump), new_pos)
        self.assertEqual(len(out), n * 40)
        for v in range(n):
            self.assertEqual(struct.unpack_from('<3f', out, v * 40),
                             new_pos[v])
            self.assertEqual(struct.unpack_from('<3f', out, v * 40 + 12),
                             (0.5, 0.5, 0.5))
            self.assertEqual(out[v * 40 + 24:v * 40 + 40], b'\xAA' * 16)

    def test_find_dump_vb0_path_cache_hit(self):
        cache = [{'vb0': 'def7af36', 'vb0_path': r'C:\d\a.buf'}]
        self.assertEqual(hs.find_dump_vb0_path('X', 'def7af36', cache),
                         r'C:\d\a.buf')

    def test_find_dump_vb0_path_glob_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, '000124-vb0=def7af36-vs=x.buf')
            with open(p, 'wb') as f:
                f.write(b'\x00' * 40)
            got = hs.find_dump_vb0_path(tmp, 'def7af36', None)
            self.assertEqual(got, p)

    def test_find_dump_vb0_path_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(hs.find_dump_vb0_path(tmp, 'deadbeef', None))


class ShrinkShiftTest(unittest.TestCase):
    def test_zero_shift_legacy_behavior(self):
        # shift=(0,0,0) keeps legacy: in-box scaled, outside unchanged
        verts = [(0.0, 0.0, 0.0), (5.0, -3.0, 2.0)]
        out = hs.shrink_positions(verts, CENTER, HALF, 0.5, falloff=0.0,
                                  shift=(0.0, 0.0, 0.0))
        self.assertAlmostEqual(out[0][0], CENTER[0] * 0.5)
        self.assertEqual(out[1], verts[1])

    def test_zero_shift_with_falloff_legacy(self):
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (1.5, 0.0, 0.0)  # d=1.5, falloff=1.0 -> t_fade=0.5, s=0.75
        out = hs.shrink_positions([p], center, half, 0.5, falloff=1.0,
                                  shift=(0.0, 0.0, 0.0))[0]
        self.assertAlmostEqual(out[0], 1.5 * 0.75)

    def test_in_box_shift_added(self):
        # d=0 -> s=scale, shift applied fully: center + delta*scale + shift
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (0.5, 0.0, 0.0)
        shift = (0.0, -0.2, 0.1)
        out = hs.shrink_positions([p], center, half, 0.5, falloff=0.3,
                                  shift=shift)[0]
        self.assertAlmostEqual(out[0], 0.5 * 0.5)          # scaled x
        self.assertAlmostEqual(out[1], -0.2)               # full shift y
        self.assertAlmostEqual(out[2], 0.1)                # full shift z

    def test_fade_band_shift_ramps_to_zero(self):
        # d=1.5, falloff=1.0 -> fade t=0.5; shift applied at (1-0.5)=0.5
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (1.5, 0.0, 0.0)
        shift = (0.0, 0.4, 0.0)
        out = hs.shrink_positions([p], center, half, 0.5, falloff=1.0,
                                  shift=shift)[0]
        self.assertAlmostEqual(out[0], 1.5 * 0.75)   # scale faded as before
        self.assertAlmostEqual(out[1], 0.4 * 0.5)    # shift half-applied
        self.assertAlmostEqual(out[2], 0.0)

    def test_band_start_full_shift(self):
        # on the surface (d=1.0): scale = scale, shift full (t_fade=0 -> 1-0)
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (1.0, 0.0, 0.0)
        shift = (0.0, 0.4, 0.0)
        out = hs.shrink_positions([p], center, half, 0.5, falloff=0.5,
                                  shift=shift)[0]
        self.assertAlmostEqual(out[0], 1.0 * 0.5)
        self.assertAlmostEqual(out[1], 0.4)  # full shift at d=1.0

    def test_band_end_no_shift(self):
        # d = 1+falloff -> t_fade=1 -> shift 0, scale 1.0: unchanged
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (1.5, 0.0, 0.0)  # d=1.5 == 1+0.5
        shift = (0.0, 0.4, 0.0)
        out = hs.shrink_positions([p], center, half, 0.5, falloff=0.5,
                                  shift=shift)
        self.assertEqual(out, [p])

    def test_outside_no_shift_no_scale(self):
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (3.0, 0.0, 0.0)  # d=3 > 1+0.5
        shift = (1.0, 2.0, 3.0)
        out = hs.shrink_positions([p], center, half, 0.5, falloff=0.5,
                                  shift=shift)
        self.assertEqual(out, [p])

    def test_falloff_zero_shift_inside_only(self):
        # falloff=0: shift applies in box, nothing outside
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        shift = (0.0, -0.3, 0.0)
        in_p = (0.2, 0.0, 0.0)
        out_p = (2.0, 0.0, 0.0)
        out = hs.shrink_positions([in_p, out_p], center, half, 0.5,
                                  falloff=0.0, shift=shift)
        self.assertAlmostEqual(out[0][0], 0.2 * 0.5)
        self.assertAlmostEqual(out[0][1], -0.3)   # shift applied
        self.assertEqual(out[1], out_p)           # outside untouched

    def test_half_zero_axis_shift_still_applies(self):
        # half (1,0,1): y excluded from distance, shift y still applies in box
        center = (0.0, 0.0, 0.0)
        half = (1.0, 0.0, 1.0)
        p = (0.5, 10.0, 0.0)  # x inside -> scaled + shifted
        shift = (0.0, 0.5, 0.0)
        out = hs.shrink_positions([p], center, half, 0.5, falloff=0.5,
                                  shift=shift)[0]
        self.assertAlmostEqual(out[0], 0.5 * 0.5)
        self.assertAlmostEqual(out[1], 10.0 * 0.5 + 0.5)  # scaled + shifted
        self.assertAlmostEqual(out[2], 0.0)


class AllVertsTransformTest(unittest.TestCase):
    def test_all_verts_uniform_scale_shift(self):
        # all_verts=True: every vertex -> center + delta*scale + shift
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        verts = [(0.0, 0.0, 0.0), (3.0, -2.0, 1.0), (10.0, 10.0, 10.0)]
        out = hs.shrink_positions(verts, center, half, 0.5, falloff=0.3,
                                  shift=(0.0, -0.2, 0.1), all_verts=True)
        self.assertAlmostEqual(out[0][0], 0.0)          # center stays scaled
        self.assertAlmostEqual(out[0][1], -0.2)         # full shift
        self.assertAlmostEqual(out[1][0], 3.0 * 0.5)    # scaled x
        self.assertAlmostEqual(out[1][1], -2.0 * 0.5 - 0.2)
        self.assertAlmostEqual(out[1][2], 1.0 * 0.5 + 0.1)
        # far outside vertex is still transformed (no box test)
        self.assertAlmostEqual(out[2][0], 10.0 * 0.5)

    def test_all_verts_transforms_outside_box(self):
        center = (0.0, 0.0, 0.0)
        half = (1.0, 1.0, 1.0)
        p = (5.0, 0.0, 0.0)  # d=5, outside box AND outside falloff band
        out = hs.shrink_positions([p], center, half, 0.5, falloff=0.5,
                                  shift=(0.0, 0.0, 0.0), all_verts=True)[0]
        self.assertAlmostEqual(out[0], 5.0 * 0.5)
        # contrast: all_verts=False leaves it untouched
        legacy = hs.shrink_positions([p], center, half, 0.5, falloff=0.5,
                                     shift=(0.0, 0.0, 0.0))[0]
        self.assertEqual(legacy, (5.0, 0.0, 0.0))

    def test_all_verts_matches_box_for_inbox(self):
        # same params: in-box verts agree between both modes
        center = (1.0, 1.0, 1.0)
        half = (2.0, 2.0, 2.0)
        p = (1.5, 0.5, 1.0)  # inside box
        args = (center, half, 0.7, 0.2, (0.1, -0.1, 0.0))
        a = hs.shrink_positions([p], *args, all_verts=True)[0]
        b = hs.shrink_positions([p], *args)[0]
        for i in range(3):
            self.assertAlmostEqual(a[i], b[i])

    def test_is_body_mesh_picks_largest(self):
        class _Data:
            def __init__(self, n):
                self.vertices = [None] * n

        class _Ob:
            def __init__(self, n):
                self.data = _Data(n)

        big = _Ob(100)
        small = _Ob(10)
        self.assertTrue(hs.is_body_mesh(big, [big, small, _Ob(50)]))
        self.assertFalse(hs.is_body_mesh(small, [big, small]))
        self.assertFalse(hs.is_body_mesh(small, []))
        self.assertTrue(hs.is_body_mesh(big, [big]))  # sole mesh is the body
        self.assertTrue(hs.is_body_mesh(big, [big, _Ob(100)]))  # tie -> body

    def test_all_verts_rule_face_full_body_box(self):
        # 新仕様: 顔メッシュは常に全頂点変形 (all_verts=True)、body は box 内
        # のみ。all_verts 判定 = not is_body_mesh で face_full_transform の
        # 値に依存しない (フラグは廃止済み)。
        class _Data:
            def __init__(self, n):
                self.vertices = [None] * n

        class _Ob:
            def __init__(self, n):
                self.data = _Data(n)

        big = _Ob(100)
        small = _Ob(10)
        meshes = [big, small]
        self.assertFalse(not hs.is_body_mesh(big, meshes))    # body -> box のみ
        self.assertTrue(not hs.is_body_mesh(small, meshes))   # 顔 -> 全頂点変形


class BoxWireframeTest(unittest.TestCase):
    def test_verts_eight_corners(self):
        center = (1.0, 2.0, 3.0)
        half = (0.5, 1.0, 2.0)
        verts = hs.box_wireframe_verts(center, half)
        self.assertEqual(len(verts), 8)
        for v in verts:
            for i in range(3):
                self.assertIn(v[i], (center[i] - half[i], center[i] + half[i]))

    def test_verts_center_symmetric(self):
        center = (1.0, 2.0, 3.0)
        half = (0.5, 1.0, 2.0)
        verts = hs.box_wireframe_verts(center, half)
        for a in verts:
            mirror = tuple(2 * center[i] - a[i] for i in range(3))
            self.assertIn(mirror, verts)

    def test_edges_twelve_no_duplicates(self):
        edges = hs.box_wireframe_edges()
        self.assertEqual(len(edges), 12)
        self.assertEqual(len(set(edges)), 12)
        deg = [0] * 8
        for a, b in edges:
            deg[a] += 1
            deg[b] += 1
        for d in deg:
            self.assertEqual(d, 3)  # cube corner touches 3 edges

    def test_bbox_center(self):
        verts = [(0.0, 0.0, 0.0), (2.0, 4.0, 6.0)]
        self.assertEqual(hs.bbox_center(verts), (1.0, 2.0, 3.0))

    def test_bbox_center_empty(self):
        self.assertIsNone(hs.bbox_center([]))

    def test_box_center_from_obj(self):
        # location + local bbox center (generic; works for any mesh object)
        obj = types.SimpleNamespace(
            location=(1.0, 2.0, 3.0),
            data=types.SimpleNamespace(vertices=[
                types.SimpleNamespace(co=(-0.5, -0.5, -0.5)),
                types.SimpleNamespace(co=(0.5, 0.5, 0.5)),
            ]),
        )
        self.assertEqual(hs.box_center_from_obj(obj), (1.0, 2.0, 3.0))

    def test_box_center_from_obj_empty(self):
        obj = types.SimpleNamespace(
            location=(0.0, 0.0, 0.0),
            data=types.SimpleNamespace(vertices=[]),
        )
        self.assertIsNone(hs.box_center_from_obj(obj))


class FaceOffsetsTest(unittest.TestCase):
    def _path(self, tmp):
        return os.path.join(tmp, 'face_offsets.json')

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            locations = {'Dump_63f702ce.001': [-0.0213, -0.1064, 0.3778],
                         'Dump_6192fe1c.001': [-0.0213, -0.1061, 0.4159]}
            n = hs.save_face_offsets(path, 'Noelle', locations)
            self.assertEqual(n, 2)
            self.assertEqual(hs.load_face_offsets(path, 'Noelle'), locations)

    def test_rounding_to_float32_precision(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_face_offsets(path, 'Noelle',
                                 {'Dump_A': [0.123456789, -1.23456789, 2.5]})
            out = hs.load_face_offsets(path, 'Noelle')['Dump_A']
            self.assertEqual(out[0], round(0.123456789, 6))
            self.assertEqual(out[1], round(-1.23456789, 6))
            self.assertEqual(out[2], 2.5)

    def test_merge_keeps_other_chars(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_face_offsets(path, 'Noelle', {'Dump_A': [1.0, 2.0, 3.0]})
            n = hs.save_face_offsets(path, 'Nilou', {'Dump_B': [4.0, 5.0, 6.0]})
            self.assertEqual(n, 1)
            self.assertEqual(hs.load_face_offsets(path, 'Noelle'),
                             {'Dump_A': [1.0, 2.0, 3.0]})
            self.assertEqual(hs.load_face_offsets(path, 'Nilou'),
                             {'Dump_B': [4.0, 5.0, 6.0]})

    def test_same_char_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_face_offsets(path, 'Noelle', {'Dump_A': [1.0, 2.0, 3.0]})
            hs.save_face_offsets(path, 'Noelle', {'Dump_A': [7.0, 8.0, 9.0],
                                                  'Dump_B': [0.0, 0.0, 0.0]})
            out = hs.load_face_offsets(path, 'Noelle')
            self.assertEqual(out['Dump_A'], [7.0, 8.0, 9.0])
            self.assertEqual(out['Dump_B'], [0.0, 0.0, 0.0])

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                hs.load_face_offsets(self._path(d), 'Noelle'), {})

    def test_corrupt_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            with open(path, 'w') as f:
                f.write('{not json!!')
            self.assertEqual(hs.load_face_offsets(path, 'Noelle'), {})

    def test_unknown_char_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_face_offsets(path, 'Noelle', {'Dump_A': [1.0, 2.0, 3.0]})
            self.assertEqual(hs.load_face_offsets(path, 'Other'), {})

    def test_invalid_entries_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            with open(path, 'w', encoding='utf-8') as f:
                f.write('{"Noelle": {"ok": [1, 2, 3], '
                        '"bad_list": [1, 2], "bad_str": "x", '
                        '"bad_type": [1, "a", 3]}}')
            self.assertEqual(hs.load_face_offsets(path, 'Noelle'),
                             {'ok': [1.0, 2.0, 3.0]})


class CharConfigTest(unittest.TestCase):
    """save_char_config / load_char_config / extract / apply roundtrip."""

    def _path(self, tmp):
        return os.path.join(tmp, 'face_offsets.json')

    def _config(self):
        return {
            'shrink_center': [-0.3, 0.0, 0.0],
            'shrink_origin': [0.0, 0.0, 0.5],
            'shrink_half': [0.5, 0.25, 0.35],
            'shrink_scale': 0.9,
            'shrink_falloff': 0.15,
            'shrink_shift': [0.0, 0.0, 0.0],
            'face_full_transform': True,
            'units': {'63f702ce': 'EYES', '6192fe1c': 'MOUTH'},
        }

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            locations = {'Dump_A': [1.0, 2.0, 3.0]}
            n = hs.save_char_config(path, 'Noelle', locations, self._config())
            self.assertEqual(n, 1)
            out = hs.load_char_config(path, 'Noelle')
            self.assertEqual(out['shrink_scale'], 0.9)
            self.assertEqual(out['units'],
                             {'63f702ce': 'EYES', '6192fe1c': 'MOUTH'})
            # locations preserved in the same entry
            self.assertEqual(hs.load_face_offsets(path, 'Noelle'),
                             {'Dump_A': [1.0, 2.0, 3.0]})

    def test_merge_keeps_other_chars(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_char_config(path, 'Noelle', {}, self._config())
            n = hs.save_char_config(path, 'Nilou', {'Dump_B': [4.0, 5.0, 6.0]},
                                    {'shrink_scale': 0.85})
            self.assertEqual(n, 1)
            self.assertEqual(hs.load_char_config(path, 'Nilou')['shrink_scale'], 0.85)
            self.assertIn('shrink_center', hs.load_char_config(path, 'Noelle'))

    def test_legacy_offsets_only_file(self):
        # A file written by the old save_face_offsets has no __config__:
        # load_char_config returns {}, load_face_offsets still works.
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_face_offsets(path, 'Noelle', {'Dump_A': [1.0, 2.0, 3.0]})
            self.assertEqual(hs.load_char_config(path, 'Noelle'), {})
            self.assertEqual(hs.load_face_offsets(path, 'Noelle'),
                             {'Dump_A': [1.0, 2.0, 3.0]})

    def test_same_char_updates_config(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_char_config(path, 'Noelle', {}, {'shrink_scale': 0.9})
            hs.save_char_config(path, 'Noelle', {}, {'shrink_scale': 0.7,
                                                     'shrink_falloff': 0.2})
            out = hs.load_char_config(path, 'Noelle')
            self.assertEqual(out['shrink_scale'], 0.7)
            self.assertEqual(out['shrink_falloff'], 0.2)

    def test_missing_and_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            self.assertEqual(hs.load_char_config(path, 'Noelle'), {})
            with open(path, 'w') as f:
                f.write('{not json!!')
            self.assertEqual(hs.load_char_config(path, 'Noelle'), {})

    def test_unknown_char_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_char_config(path, 'Noelle', {}, self._config())
            self.assertEqual(hs.load_char_config(path, 'Nilou'), {})

    def test_extract_char_config(self):
        props = types.SimpleNamespace(
            shrink_center=(0.1, 0.2, 0.3), shrink_origin=(0.0, 0.0, 0.5),
            shrink_half=(0.5, 0.25, 0.35), shrink_scale=0.88,
            shrink_falloff=0.2, shrink_shift=(0.0, 0.0, 0.0),
            face_full_transform=False,
            eye_sink=0.005, eye_sink_pad=0.01,
            eye_region_min=(0.037, 0.382, -0.1),
            eye_region_max=(0.057, 0.444, 0.1),
        )
        cfg = hs.extract_char_config(props)
        self.assertEqual(cfg['shrink_center'], [0.1, 0.2, 0.3])
        self.assertEqual(cfg['shrink_scale'], 0.88)
        self.assertFalse(cfg['face_full_transform'])
        self.assertEqual(cfg['eye_region_min'], [0.037, 0.382, -0.1])
        self.assertEqual(cfg['eye_region_max'], [0.057, 0.444, 0.1])

    def test_apply_char_config_partial(self):
        props = types.SimpleNamespace(
            shrink_center=(0.0, 0.0, 0.0), shrink_scale=1.0,
        )
        n = hs.apply_char_config(props, {'shrink_center': [0.5, 0.0, 0.0],
                                         'shrink_scale': 0.75,
                                         'units': {'63f702ce': 'EYES'}})
        # units is not a props key -> skipped
        self.assertEqual(n, 2)
        self.assertEqual(props.shrink_center, (0.5, 0.0, 0.0))
        self.assertEqual(props.shrink_scale, 0.75)

    def test_apply_char_config_missing_keys_skipped(self):
        props = types.SimpleNamespace(shrink_center=(0.0, 0.0, 0.0),
                                      shrink_scale=1.0)
        n = hs.apply_char_config(props, {'shrink_scale': 0.6,
                                         'no_such_key': 1.0})
        self.assertEqual(n, 1)
        self.assertEqual(props.shrink_scale, 0.6)
        self.assertEqual(props.shrink_center, (0.0, 0.0, 0.0))


class ResolveCharConfigTest(unittest.TestCase):
    """resolve_char_config merges the shared __default__ base with the
    per-character config (character wins on key conflicts)."""

    def _path(self, tmp):
        return os.path.join(tmp, 'face_offsets.json')

    def test_default_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_char_config(path, hs.DEFAULT_CONFIG_KEY, {},
                                {'shrink_scale': 0.9})
            self.assertEqual(hs.resolve_char_config(path, 'Noelle'),
                             {'shrink_scale': 0.9})

    def test_char_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_char_config(path, 'Noelle', {}, {'shrink_scale': 0.85})
            self.assertEqual(hs.resolve_char_config(path, 'Noelle'),
                             {'shrink_scale': 0.85})

    def test_default_base_char_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_char_config(path, hs.DEFAULT_CONFIG_KEY, {},
                                {'shrink_scale': 0.9, 'shrink_falloff': 0.2})
            hs.save_char_config(path, 'Noelle', {}, {'shrink_scale': 0.85})
            out = hs.resolve_char_config(path, 'Noelle')
            self.assertEqual(out['shrink_scale'], 0.85)   # char wins
            self.assertEqual(out['shrink_falloff'], 0.2)  # default fills rest

    def test_none_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(hs.resolve_char_config(self._path(d), 'Noelle'),
                             {})

    def test_default_saved_via_char_config_api(self):
        # the save path used by the Save as Default operator
        with tempfile.TemporaryDirectory() as d:
            path = self._path(d)
            hs.save_char_config(path, hs.DEFAULT_CONFIG_KEY, {},
                                {'shrink_scale': 0.9})
            self.assertEqual(hs.load_char_config(path, hs.DEFAULT_CONFIG_KEY),
                             {'shrink_scale': 0.9})


class SelectImportTest(unittest.TestCase):
    """select_import_pairs picks body + face candidates."""

    def _pair(self, vb0, vert_count):
        return {'vb0': vb0, 'ib': 'x', 'frame': '000001',
                'vert_count': vert_count, 'index_count': 100,
                'vb0_path': '', 'ib_path': ''}

    def test_body_plus_face_candidates(self):
        pairs = [self._pair('aabbccdd', 15965),   # body
                 self._pair('63f702ce', 1083),    # eyes
                 self._pair('6192fe1c', 877),     # mouth
                 self._pair('ddf54429', 56)]      # brow
        out = hs.select_import_pairs(pairs)
        self.assertEqual([p['vb0'] for p in out],
                         ['aabbccdd', '63f702ce', '6192fe1c', 'ddf54429'])

    def test_tiny_skipped(self):
        pairs = [self._pair('aabbccdd', 15965),
                 self._pair('tiny1', 20)]
        out = hs.select_import_pairs(pairs)
        self.assertEqual([p['vb0'] for p in out], ['aabbccdd'])

    def test_huge_non_body_skipped(self):
        pairs = [self._pair('body', 150000),  # biggest = body
                 self._pair('huge1', 120000)]  # 4MB class, not biggest
        out = hs.select_import_pairs(pairs)
        self.assertEqual([p['vb0'] for p in out], ['body'])

    def test_empty(self):
        self.assertEqual(hs.select_import_pairs([]), [])

    def test_body_always_included_even_if_huge(self):
        pairs = [self._pair('body', 150000),  # biggest = body
                 self._pair('face', 500)]
        out = hs.select_import_pairs(pairs)
        self.assertEqual([p['vb0'] for p in out], ['body', 'face'])





class EyeSinkTest(unittest.TestCase):
    """eye_sink_positions sinks head verts in the eyes region back along x."""

    # Noelle-measured eyes bbox (display coords, location-inclusive)
    BBOX = ((-0.0983, 0.0076, 0.3867), (0.0579, 0.0704, 0.4866))
    PAD = 0.01
    SINK = 0.005

    def test_inside_region_moves_negative_x(self):
        p = (0.03, 0.04, 0.45)  # inside y/z bbox, x <= bmax.x + pad
        out = hs.eye_sink_positions([p], [self.BBOX], self.PAD, self.SINK)
        self.assertEqual(out[0], (p[0] - self.SINK, p[1], p[2]))

    def test_outside_y_unchanged(self):
        p = (0.03, 0.2, 0.45)  # y far above bbox
        out = hs.eye_sink_positions([p], [self.BBOX], self.PAD, self.SINK)
        self.assertEqual(out[0], p)

    def test_outside_z_unchanged(self):
        p = (0.03, 0.04, 0.8)  # z far above bbox
        out = hs.eye_sink_positions([p], [self.BBOX], self.PAD, self.SINK)
        self.assertEqual(out[0], p)

    def test_beyond_x_max_unchanged(self):
        p = (0.2, 0.04, 0.45)  # x > bmax.x + pad
        out = hs.eye_sink_positions([p], [self.BBOX], self.PAD, self.SINK)
        self.assertEqual(out[0], p)

    def test_x_at_boundary_is_included(self):
        p = (self.BBOX[1][0] + self.PAD, 0.04, 0.45)  # x == bmax.x + pad
        out = hs.eye_sink_positions([p], [self.BBOX], self.PAD, self.SINK)
        self.assertEqual(out[0], (p[0] - self.SINK, p[1], p[2]))

    def test_pad_widens_region(self):
        # y just outside bbox but inside bbox+pad: moved with pad, kept with 0
        p = (0.03, 0.075, 0.45)  # bmax.y=0.0704, pad=0.01 -> 0.0804
        out = hs.eye_sink_positions([p], [self.BBOX], self.PAD, self.SINK)
        self.assertEqual(out[0][0], p[0] - self.SINK)
        out0 = hs.eye_sink_positions([p], [self.BBOX], 0.0, self.SINK)
        self.assertEqual(out0[0], p)

    def test_zero_sink_keeps_all(self):
        verts = [(0.03, 0.04, 0.45), (0.2, 0.2, 0.2), (-1.0, -1.0, -1.0)]
        out = hs.eye_sink_positions(verts, [self.BBOX], self.PAD, 0.0)
        self.assertEqual(out, verts)

    def test_mixed_verts(self):
        verts = [(0.03, 0.04, 0.45), (0.2, 0.2, 0.2), (-0.05, 0.03, 0.40)]
        out = hs.eye_sink_positions(verts, [self.BBOX], self.PAD, self.SINK)
        self.assertEqual(out[0][0], verts[0][0] - self.SINK)
        self.assertEqual(out[1], verts[1])
        self.assertEqual(out[2][0], verts[2][0] - self.SINK)

    def test_multi_bbox_any_match(self):
        # second bbox covers the vert the first one misses
        other = ((0.2, 0.2, 0.7), (0.3, 0.3, 0.8))
        verts = [(0.25, 0.25, 0.75), (0.03, 0.04, 0.45)]
        out = hs.eye_sink_positions(verts, [self.BBOX, other], self.PAD,
                                    self.SINK)
        self.assertEqual(out[0][0], verts[0][0] - self.SINK)
        self.assertEqual(out[1][0], verts[1][0] - self.SINK)

    def test_multi_bbox_miss_all_unchanged(self):
        other = ((0.5, 0.5, 0.7), (0.6, 0.6, 0.8))
        p = (0.7, 0.55, 0.75)  # x beyond both bbox x_max + pad
        out = hs.eye_sink_positions([p], [self.BBOX, other], self.PAD,
                                    self.SINK)
        self.assertEqual(out[0], p)

    def test_empty_bboxes_unchanged(self):
        p = (0.03, 0.04, 0.45)
        out = hs.eye_sink_positions([p], [], self.PAD, self.SINK)
        self.assertEqual(out[0], p)


class _FakeObj:
    """Minimal bpy object stand-in for eye_region_bboxes tests."""

    def __init__(self, role, location, verts, vb0=None):
        self.type = 'MESH'
        self.location = location
        self._role = role
        self._vb0 = vb0
        self.data = types.SimpleNamespace(vertices=[
            types.SimpleNamespace(co=v) for v in verts])

    def get(self, key, default=None):
        if key == 'hs_role':
            return self._role
        if key == 'hs_vb0_hash':
            return self._vb0 if self._vb0 is not None else default
        return default


class EyeRegionBBoxesTest(unittest.TestCase):
    """eye_region_bboxes collects display-space bboxes of EYES-role meshes."""

    def test_no_eyes_returns_empty(self):
        objs = [_FakeObj('BODY', (0.0, 0.0, 0.0), [(0.0, 0.0, 0.0)]),
                _FakeObj('MOUTH', (0.0, 0.0, 0.0), [(0.0, 0.0, 0.0)])]
        self.assertEqual(hs.eye_region_bboxes(objs), [])

    def test_empty_mesh_list(self):
        self.assertEqual(hs.eye_region_bboxes([]), [])

    def test_single_eyes_bbox(self):
        objs = [_FakeObj('EYES', (0.1, 0.2, 0.3),
                         [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)])]
        boxes = hs.eye_region_bboxes(objs)
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0],
                         ((0.1, 0.2, 0.3), (1.1, 2.2, 3.3)))

    def test_eyes_location_included(self):
        # negative coords + positive location -> min from coords+loc
        objs = [_FakeObj('EYES', (-0.5, 0.0, 0.0),
                         [(-0.1, -0.2, -0.3), (0.1, 0.2, 0.3)])]
        boxes = hs.eye_region_bboxes(objs)
        self.assertEqual(boxes[0],
                         ((-0.6, -0.2, -0.3), (-0.4, 0.2, 0.3)))

    def test_skips_non_eyes_roles(self):
        objs = [_FakeObj('BODY', (0.0, 0.0, 0.0), [(0.0, 0.0, 0.0)]),
                _FakeObj('EYES', (0.0, 0.0, 0.0), [(1.0, 1.0, 1.0)]),
                _FakeObj('BROW', (0.0, 0.0, 0.0), [(2.0, 2.0, 2.0)])]
        boxes = hs.eye_region_bboxes(objs)
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0], ((1.0, 1.0, 1.0), (1.0, 1.0, 1.0)))

    def test_multiple_eyes_returns_multiple_bboxes(self):
        objs = [_FakeObj('EYES', (0.0, 0.0, 0.0), [(0.0, 0.0, 0.0)]),
                _FakeObj('EYES', (0.0, 0.0, 0.0), [(5.0, 5.0, 5.0)])]
        boxes = hs.eye_region_bboxes(objs)
        self.assertEqual(len(boxes), 2)

    def test_empty_eyes_mesh_skipped(self):
        objs = [_FakeObj('EYES', (0.0, 0.0, 0.0), [])]
        self.assertEqual(hs.eye_region_bboxes(objs), [])


class ResolveEyeBBoxesTest(unittest.TestCase):
    """resolve_eye_bboxes: a user-set region overrides the automatic EYES bboxes."""

    AUTO = [((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
            ((2.0, 2.0, 2.0), (3.0, 3.0, 3.0))]

    def test_unset_returns_auto(self):
        self.assertEqual(hs.resolve_eye_bboxes(self.AUTO, (0, 0, 0), (0, 0, 0)),
                         self.AUTO)

    def test_set_returns_single_override(self):
        out = hs.resolve_eye_bboxes(self.AUTO, (0.1, 0.2, 0.3), (1.1, 2.2, 3.3))
        self.assertEqual(out, [((0.1, 0.2, 0.3), (1.1, 2.2, 3.3))])

    def test_none_returns_auto(self):
        self.assertEqual(hs.resolve_eye_bboxes(self.AUTO, None, None),
                         self.AUTO)

    def test_mixed_none_returns_auto(self):
        # a half-set region is treated as unset (defensive: never half-applied)
        self.assertEqual(hs.resolve_eye_bboxes(self.AUTO, None, (1.0, 1.0, 1.0)),
                         self.AUTO)
        self.assertEqual(hs.resolve_eye_bboxes(self.AUTO, (0.0, 0.0, 0.0), None),
                         self.AUTO)

    def test_empty_auto_list(self):
        self.assertEqual(hs.resolve_eye_bboxes([], (0.1, 0.2, 0.3),
                                               (1.1, 2.2, 3.3)),
                         [((0.1, 0.2, 0.3), (1.1, 2.2, 3.3))])


class SelectionDisplayBBoxTest(unittest.TestCase):
    """selection_display_bbox computes display-space bbox of chosen verts."""

    def test_selected_verts_only(self):
        mesh = _FakeObj('BODY', (0.0, 0.0, 0.0),
                        [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0),
                         (4.0, 5.0, 6.0)]).data
        out = hs.selection_display_bbox(mesh, [0, 2], (0.0, 0.0, 0.0))
        self.assertEqual(out, ((0.0, 0.0, 0.0), (4.0, 5.0, 6.0)))

    def test_offset_included(self):
        mesh = _FakeObj('BODY', (0.0, 0.0, 0.0),
                        [(-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)]).data
        out = hs.selection_display_bbox(mesh, [0, 1], (10.0, 0.5, -0.5))
        self.assertEqual(out, ((9.0, -0.5, -1.5), (11.0, 1.5, 0.5)))

    def test_empty_returns_none(self):
        mesh = _FakeObj('BODY', (0.0, 0.0, 0.0), [(0.0, 0.0, 0.0)]).data
        self.assertIsNone(hs.selection_display_bbox(mesh, [], (0.0, 0.0, 0.0)))

    def test_single_vert(self):
        mesh = _FakeObj('BODY', (0.0, 0.0, 0.0), [(2.0, 3.0, 4.0)]).data
        out = hs.selection_display_bbox(mesh, [0], (0.0, 0.0, 0.0))
        self.assertEqual(out, ((2.0, 3.0, 4.0), (2.0, 3.0, 4.0)))


class MatchFaceOffsetsTest(unittest.TestCase):
    """_match_face_offsets: 顔メッシュを body に重ねる loc の境界マッチング。"""

    @staticmethod
    def _grid(n=10, spacing=0.1):
        return [(x * spacing, y * spacing, z * spacing)
                for x in range(n) for y in range(n) for z in range(n)]

    def _body(self):
        return types.SimpleNamespace(
            location=(0.0, 0.0, 0.0),
            data=types.SimpleNamespace(vertices=[
                types.SimpleNamespace(co=v) for v in self._grid()]))

    def _z0_verts(self):
        return [v for v in self._grid() if abs(v[2]) < 1e-9]

    def test_offset_T_recovered(self):
        # 顔は body の z=0 層から T だけずれた位置にある (正しい loc = T)
        T = (0.03, -0.05, 0.02)
        face_verts = [(v[0] - T[0], v[1] - T[1], v[2] - T[2])
                      for v in self._z0_verts()]
        face = _FakeObj('EYES', (0.0, 0.0, 0.0), face_verts, vb0='63f702ce')
        out = hs._match_face_offsets(
            self._body(), [face], {'63f702ce': (0.0, 0.0, 0.0)},
            dist_threshold=0.08)
        for i in range(3):
            self.assertAlmostEqual(out['63f702ce'][i], T[i], delta=0.002)

    def test_zero_offset_recovered(self):
        # 顔が body と完全一致 → loc は 0 に収束 (初期値の誤差を打ち消す)
        face = _FakeObj('EYES', (0.0, 0.0, 0.0), self._z0_verts(),
                        vb0='63f702ce')
        out = hs._match_face_offsets(
            self._body(), [face], {'63f702ce': (0.02, -0.01, 0.03)},
            dist_threshold=0.08)
        for i in range(3):
            self.assertAlmostEqual(out['63f702ce'][i], 0.0, delta=0.002)

    def test_far_face_unchanged(self):
        # 境界ペア 0 件 (body から遠い) → loc は初期値のまま変化しない
        far = [(v[0] + 5.0, v[1] + 5.0, v[2] + 5.0) for v in self._grid()]
        face = _FakeObj('EYES', (0.0, 0.0, 0.0), far, vb0='63f702ce')
        initial = (0.1, 0.2, 0.3)
        out = hs._match_face_offsets(
            self._body(), [face], {'63f702ce': initial})
        self.assertEqual(out['63f702ce'], initial)

    def test_delta_monotonic_decrease(self):
        # 反復ごとの更新量 (delta) が単調減少する (収束性)
        T = (0.03, -0.05, 0.02)
        face_verts = [(v[0] - T[0], v[1] - T[1], v[2] - T[2])
                      for v in self._z0_verts()]
        face = _FakeObj('EYES', (0.0, 0.0, 0.0), face_verts, vb0='63f702ce')
        orig_median = hs.np.median
        deltas = []

        def spy_median(a, axis=0):
            m = orig_median(a, axis=axis)
            deltas.append(float(np.max(np.abs(m))))
            return m

        hs.np.median = spy_median
        try:
            hs._match_face_offsets(
                self._body(), [face], {'63f702ce': (0.0, 0.0, 0.0)},
                dist_threshold=0.08)
        finally:
            hs.np.median = orig_median
        self.assertGreater(len(deltas), 1)  # 複数反復した
        self.assertTrue(all(deltas[i] >= deltas[i + 1]
                            for i in range(len(deltas) - 1)))


class FaceBBoxCenterTest(unittest.TestCase):
    """_face_bbox_center / _auto_face_pivot / _auto_face_shrink_center:
    v1.9.2 以降は BODY 頭部 (position_vb 空間) 基準。BODY 無しは顔基準フォールバック。"""

    def _body(self):
        # BODY: z 0..19 の 20 頂点。頭部 (上位 35%) = z >= 6.65 → 頂点 7..19
        return _FakeObj('BODY', (0.0, 0.0, 0.0),
                        [(float(i), float(i), float(i)) for i in range(20)])

    def _face(self):
        # 表示空間 (co+loc): x 0..0 / y 0.1..0.3 / z 0.3..0.8
        return _FakeObj('EYES', (0.0, 0.2, 0.3),
                        [(0.0, 0.0, 0.0), (0.0, -0.1, 0.2), (0.0, 0.1, 0.5)])

    def test_face_mesh_returns_center(self):
        # 配置済み顔メッシュ (loc≠0) の表示空間 bbox 中心 (x,y,z) を返す
        out = hs._face_bbox_center([self._body(), self._face()])
        self.assertEqual(out, (0.0, 0.2, 0.55))  # y: (0.1+0.3)/2 / z: (0.3+0.8)/2

    def test_body_only_returns_none(self):
        self.assertIsNone(hs._face_bbox_center([self._body()]))

    def test_face_with_zero_loc_excluded(self):
        # loc=(0,0,0) の顔 (未配置のダンプ原位置) は対象外 → None
        face = _FakeObj('EYES', (0.0, 0.0, 0.0), [(0.0, -0.5, 0.4)])
        self.assertIsNone(hs._face_bbox_center([self._body(), face]))

    def test_auto_pivot_sets_body_head_center(self):
        # BODY 頭部 bbox 中心 (16,16,16) が pivot になる (顔基準ではない)
        props = types.SimpleNamespace(shrink_origin=(0.0, 0.0, 0.0))
        hs._auto_face_pivot(props, [self._body(), self._face()])
        self.assertEqual(props.shrink_origin, (16.0, 16.0, 16.0))

    def test_auto_pivot_body_only_sets_head(self):
        props = types.SimpleNamespace(shrink_origin=(0.5, 0.5, 0.5))
        hs._auto_face_pivot(props, [self._body()])
        self.assertEqual(props.shrink_origin, (16.0, 16.0, 16.0))

    def test_auto_pivot_single_face_treated_as_body(self):
        # is_body_mesh は最大頂点数で判定: 単一メッシュは BODY 扱い → 頭部基準
        props = types.SimpleNamespace(shrink_origin=(0.0, 0.0, 0.0))
        hs._auto_face_pivot(props, [self._face()])
        self.assertAlmostEqual(props.shrink_origin[0], 0.0, places=6)
        self.assertAlmostEqual(props.shrink_origin[1], 0.3, places=6)
        self.assertAlmostEqual(props.shrink_origin[2], 0.8, places=6)

    def test_auto_pivot_no_mesh_unchanged(self):
        props = types.SimpleNamespace(shrink_origin=(0.5, 0.5, 0.5))
        hs._auto_face_pivot(props, [])
        self.assertEqual(props.shrink_origin, (0.5, 0.5, 0.5))

    def test_auto_center_sets_body_head_box(self):
        # box 中心 = BODY 頭部 bbox 中心、half = 頭部 bbox の半分
        props = types.SimpleNamespace(shrink_center=(0.5, 0.0, 0.0),
                                      shrink_half=(0.2, 0.2, 0.2))
        hs._auto_face_shrink_center(props, [self._body(), self._face()])
        self.assertEqual(props.shrink_center, (16.0, 16.0, 16.0))
        self.assertEqual(props.shrink_half, (3.0, 3.0, 3.0))

    def test_auto_center_single_face_treated_as_body(self):
        # 単一メッシュは BODY 扱い → 頭部 bbox 基準 (half は 0.15 にクランプ)
        props = types.SimpleNamespace(shrink_center=(0.5, 0.0, 0.0),
                                      shrink_half=(0.2, 0.2, 0.2))
        hs._auto_face_shrink_center(props, [self._face()])
        self.assertAlmostEqual(props.shrink_center[0], 0.0, places=6)
        self.assertAlmostEqual(props.shrink_center[1], 0.3, places=6)
        self.assertAlmostEqual(props.shrink_center[2], 0.8, places=6)
        self.assertEqual(props.shrink_half, (0.15, 0.15, 0.15))

    def test_auto_center_no_mesh_unchanged(self):
        props = types.SimpleNamespace(shrink_center=(0.5, 0.0, 0.0),
                                      shrink_half=(0.2, 0.2, 0.2))
        hs._auto_face_shrink_center(props, [])
        self.assertEqual(props.shrink_center, (0.5, 0.0, 0.0))
        self.assertEqual(props.shrink_half, (0.2, 0.2, 0.2))


class BodyHeadBBoxTest(unittest.TestCase):
    """_body_head_bbox: BODY メッシュの頭部 (z 上位 35%) の bbox を返す。"""

    def _body(self):
        return _FakeObj('BODY', (0.0, 0.0, 0.0),
                        [(float(i), float(i), float(i)) for i in range(20)])

    def _face(self):
        return _FakeObj('EYES', (0.0, 0.2, 0.3),
                        [(0.0, 0.0, 0.0), (0.0, -0.1, 0.2), (0.0, 0.1, 0.5)])

    def test_returns_head_region_bbox(self):
        # z 0..19 の上位 35% → z >= 12.35 → 頂点 13..19 → center (16,16,16) / half (3,3,3)
        out = hs._body_head_bbox([self._body(), self._face()])
        self.assertEqual(out, ((16.0, 16.0, 16.0), (3.0, 3.0, 3.0)))

    def test_single_face_treated_as_body(self):
        # is_body_mesh は最大頂点数で判定: 単一メッシュは BODY 扱い
        # face 表示空間 z 0.3..0.8 → 上位 35% (z >= 0.625) は (0, 0.3, 0.8) のみ
        out = hs._body_head_bbox([self._face()])
        self.assertAlmostEqual(out[0][0], 0.0, places=6)
        self.assertAlmostEqual(out[0][1], 0.3, places=6)
        self.assertAlmostEqual(out[0][2], 0.8, places=6)
        self.assertEqual(out[1], (0.0, 0.0, 0.0))

    def test_empty_returns_none(self):
        self.assertIsNone(hs._body_head_bbox([]))

    def test_half_clamped_to_minimum(self):
        # 頭部が極小 (half < 0.15) でも shrink_half は 0.15 以上にクランプ
        tiny = _FakeObj('BODY', (0.0, 0.0, 0.0),
                        [(0.0, 0.0, 0.0), (0.0, 0.0, 0.1), (0.0, 0.0, 0.2)])
        props = types.SimpleNamespace(shrink_center=(0.0, 0.0, 0.0),
                                      shrink_half=(0.0, 0.0, 0.0))
        hs._auto_face_shrink_center(props, [tiny])
        self.assertEqual(props.shrink_half, (0.15, 0.15, 0.15))


class CleanExportDirTest(unittest.TestCase):
    """_clean_export_dir removes stale files from a previous export mode."""

    def _make_dir(self):
        return tempfile.mkdtemp(prefix='hs_clean_')

    def test_removes_stale_export_files_keeps_others(self):
        d = self._make_dir()
        for fn in ('Noelle.ini', 'NoelleHead.hlsl',
                   'NoelleBodyPosition.buf', 'NoelleBodyBase.buf',
                   'NoelleEyesKey.buf',
                   'OtherChar.ini', 'OtherCharBodyBase.buf', 'notes.txt'):
            with open(os.path.join(d, fn), 'w') as f:
                f.write('x')
        removed = hs._clean_export_dir(d, 'Noelle')
        for fn in ('Noelle.ini', 'NoelleHead.hlsl',
                   'NoelleBodyPosition.buf', 'NoelleBodyBase.buf',
                   'NoelleEyesKey.buf'):
            self.assertFalse(os.path.exists(os.path.join(d, fn)), fn)
        for fn in ('OtherChar.ini', 'OtherCharBodyBase.buf', 'notes.txt'):
            self.assertTrue(os.path.exists(os.path.join(d, fn)), fn)
        self.assertEqual(removed, 5)

    def test_missing_files_ignored(self):
        d = self._make_dir()
        self.assertEqual(hs._clean_export_dir(d, 'Noelle'), 0)


class PositionVbScanTest(unittest.TestCase):
    """scan_dump_dir: -vs=<position_vs>- 付き vb0 を position_vb として記録。"""

    DRAW_VS = '95aa6cdb84eb7b99'

    def _make_dump_dir(self):
        d = tempfile.mkdtemp(prefix='hs_pv_')
        vb = struct.pack('<3f', 0.0, 0.0, 0.0) + b'\x00' * 28  # 1 vert (stride 40)
        # draw ペア (frame 000001): vb0 + ib
        with open(os.path.join(d, f'000001-vb0=def7af36-vs={self.DRAW_VS}-ps=20872172fd23eeed.buf'),
                  'wb') as f:
            f.write(vb * 4)  # 4 verts
        with open(os.path.join(d, '000001-ib=11223344.buf'), 'wb') as f:
            f.write(struct.pack('<6H', 0, 1, 2, 1, 2, 3))
        # position_vb (スキニングパス、IB 無し): 4 verts
        with open(os.path.join(d, '000001-vb0=d1384d15-vs=653c63ba4a73ca8b.buf'),
                  'wb') as f:
            f.write(vb * 4)
        # VS 不一致の vb0 (position_vb ではない)
        with open(os.path.join(d, f'000001-vb0=aaaa1111-vs={self.DRAW_VS}.buf'),
                  'wb') as f:
            f.write(vb * 4)
        return d

    def test_position_vb_recorded(self):
        d = self._make_dump_dir()
        hs.scan_dump_dir(d)
        pv = hs._dump_cache['position_vb']
        self.assertIn('d1384d15', pv)
        self.assertEqual(pv['d1384d15']['vert_count'], 4)
        self.assertTrue(
            pv['d1384d15']['path'].endswith('653c63ba4a73ca8b.buf'))

    def test_non_position_vs_excluded(self):
        d = self._make_dump_dir()
        hs.scan_dump_dir(d)
        pv = hs._dump_cache['position_vb']
        self.assertNotIn('aaaa1111', pv)
        self.assertNotIn('def7af36', pv)  # draw vb0 も対象外

    def test_empty_dir_no_position_vb(self):
        with tempfile.TemporaryDirectory() as d:
            hs.scan_dump_dir(d)
            self.assertEqual(hs._dump_cache['position_vb'], {})

    def test_real_noelle_dump_recognizes_d1384d15(self):
        real = os.path.normpath(os.path.join(
            SCRIPT_DIR, '..', 'assets', 'Dump', 'Noelle'))
        if not os.path.isdir(real):
            self.skipTest('real Noelle dump not present')
        hs.scan_dump_dir(real)
        pv = hs._dump_cache['position_vb']
        self.assertIn('d1384d15', pv)
        self.assertEqual(pv['d1384d15']['vert_count'], 15965)


class FindPositionVbTest(unittest.TestCase):
    """find_position_vb: 頂点数一致の position_vb エントリを返す。"""

    CACHE = {'position_vb': {
        'd1384d15': {'path': 'x.buf', 'vert_count': 15965,
                     'vs': '653c63ba4a73ca8b'},
        'aaa11111': {'path': 'y.buf', 'vert_count': 1083,
                     'vs': '653c63ba4a73ca8b'},
    }}

    def test_matching_vert_count(self):
        out = hs.find_position_vb(self.CACHE, 'def7af36', 15965)
        self.assertEqual(out['vb_hash'], 'd1384d15')
        self.assertEqual(out['path'], 'x.buf')
        self.assertEqual(out['vert_count'], 15965)

    def test_mismatch_returns_none(self):
        self.assertIsNone(hs.find_position_vb(self.CACHE, 'def7af36', 999))

    def test_empty_cache_returns_none(self):
        self.assertIsNone(hs.find_position_vb({}, 'def7af36', 15965))

    def test_missing_position_vb_key_returns_none(self):
        self.assertIsNone(hs.find_position_vb({'pairs': []}, 'def7af36', 15965))


class ExportPositionVbIniTest(unittest.TestCase):
    """BODY + position_vb 対応時: ini の TextureOverride hash は position_vb。

    フォールバック (position_vb 無し) では従来の draw_vb hash のまま。
    build_diff_ini は units の vb_hash をそのまま使う。
    """

    def test_ini_uses_position_vb_hash(self):
        units = [{'name': 'NoelleBody', 'vb_hash': 'd1384d15',
                  'vert_count': 15965, 'role': 'BODY'}]
        ini = hs.build_diff_ini('Noelle', units)
        self.assertIn('[TextureOverrideNoelleBody]', ini)
        self.assertIn('hash = d1384d15', ini)
        self.assertIn('vb0 = ResourceNoelleBodyPosition', ini)
        self.assertNotIn('def7af36', ini)

    def test_fallback_keeps_draw_vb_hash(self):
        units = [{'name': 'NoelleBody', 'vb_hash': 'def7af36',
                  'vert_count': 15965, 'role': 'BODY'}]
        ini = hs.build_diff_ini('Noelle', units)
        self.assertIn('hash = def7af36', ini)
        self.assertNotIn('d1384d15', ini)


class PositionVbTransformTest(unittest.TestCase):
    """position_vb は y-up モデルローカル座標: 変換は draw_vb (x-down) と別。

    position_vb -> display: (dx, dy, dz) = (-lx, -lz, +ly)
    display -> position_vb: (lx, ly, lz) = (-dx, +dz, -dy)
    """

    def test_position_vb_to_display(self):
        # local (0.1, 1.0, 0.2): 上 (+y) が display の上 (+z)、左右反転、前後反転
        self.assertEqual(hs.position_vb_to_display((0.1, 1.0, 0.2)),
                         (-0.1, -0.2, 1.0))

    def test_roundtrip_inverse(self):
        p = (0.3, -0.5, 1.7)
        out = hs.position_vb_to_display(hs.display_to_position_vb(p))
        self.assertAlmostEqual(out[0], p[0], places=6)
        self.assertAlmostEqual(out[1], p[1], places=6)
        self.assertAlmostEqual(out[2], p[2], places=6)
        back = hs.display_to_position_vb(hs.position_vb_to_display(p))
        self.assertAlmostEqual(back[0], p[0], places=6)
        self.assertAlmostEqual(back[1], p[1], places=6)
        self.assertAlmostEqual(back[2], p[2], places=6)

    def test_game_to_display_unchanged(self):
        # draw_vb (game space) の変換は従来どおり (x-down -> z-up)
        self.assertEqual(hs.game_to_display((1.0, 0.0, 0.0)), (0.0, 0.0, -1.0))
        self.assertEqual(hs.game_to_display((0.0, 0.0, 1.0)), (1.0, 0.0, 0.0))


if __name__ == '__main__':
    unittest.main(verbosity=2)
