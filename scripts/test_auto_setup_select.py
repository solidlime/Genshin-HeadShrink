"""Unit tests for the 1-click auto setup helpers (bpy-independent).

Covers: select_import_pairs garbage exclusion (4MB-class buffers), body
selection (largest / single-pair) and head_center_from_verts NaN guard.

Run: python test_auto_setup_select.py
"""
import os
import sys
import types
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# --- minimal bpy stub: only needed for class definitions to import ---
if 'bpy' not in sys.modules:
    bpy_stub = types.ModuleType('bpy')

    def _prop_fn(*args, **kwargs):
        return None

    class _Base:
        pass

    bpy_stub.props = types.SimpleNamespace(
        StringProperty=_prop_fn, FloatVectorProperty=_prop_fn,
        EnumProperty=_prop_fn, PointerProperty=_prop_fn,
        CollectionProperty=_prop_fn, PropertyGroup=_Base,
        FloatProperty=_prop_fn, BoolProperty=_prop_fn,
        IntProperty=_prop_fn,
    )
    bpy_stub.types = types.SimpleNamespace(
        PropertyGroup=_Base, Operator=_Base, Panel=_Base, UIList=_Base)
    bpy_stub.utils = types.SimpleNamespace(
        register_class=lambda c: None, unregister_class=lambda c: None)
    bpy_stub.path = types.SimpleNamespace(abspath=lambda p: p)
    bpy_stub.data = types.SimpleNamespace()
    bpy_stub.context = types.SimpleNamespace()
    sys.modules['bpy'] = bpy_stub

import headshrink_addon as hs  # noqa: E402


def _pair(vb0, vert_count):
    """Minimal dump pair dict (scan_dump_dir shape, only vert_count used)."""
    return {'vb0': vb0, 'ib': 'ib', 'frame': 0, 'vert_count': vert_count,
            'index_count': 0, 'vb0_path': 'x', 'ib_path': 'y'}


class SelectImportPairsTest(unittest.TestCase):

    def test_noelle_garbage_excluded(self):
        # 実測 Noelle ダンプ: 911ff708 (104857v) / def7af36 (15965v) /
        # 63f702ce (1083v) / 6192fe1c (877v) / ddf54429 (56v) + ゴミ 2 個目 (120000v)
        pairs = [
            _pair('911ff708', 104857),  # 4MB クラスゴミ
            _pair('def7af36', 15965),   # ボディ
            _pair('63f702ce', 1083),    # EYES
            _pair('6192fe1c', 877),     # MOUTH
            _pair('ddf54429', 56),      # BROW
            _pair('garbage2', 120000),  # ゴミ 2 個目 (複数ゴミ対応)
        ]
        out = hs.select_import_pairs(pairs)
        self.assertEqual([p['vb0'] for p in out],
                         ['def7af36', '63f702ce', '6192fe1c', 'ddf54429'])

    def test_no_garbage_largest_is_body(self):
        # ゴミなし: 従来通り最大 = ボディ + 顔候補 (50..3000)
        pairs = [_pair('a', 15965), _pair('b', 1083), _pair('c', 877),
                 _pair('d', 56)]
        out = hs.select_import_pairs(pairs)
        self.assertEqual([p['vb0'] for p in out], ['a', 'b', 'c', 'd'])

    def test_single_pair_is_body(self):
        pairs = [_pair('only', 15965)]
        out = hs.select_import_pairs(pairs)
        self.assertEqual([p['vb0'] for p in out], ['only'])

    def test_empty_returns_empty(self):
        self.assertEqual(hs.select_import_pairs([]), [])

    def test_units_map_filters_to_registered(self):
        # units 登録 = キャラメッシュ。登録外 (顔サイズ・ゴミ) は除外される
        pairs = [
            _pair('def7af36', 15965),   # ボディ (units 有り・最大)
            _pair('63f702ce', 1083),    # EYES (units 有り)
            _pair('6192fe1c', 877),     # MOUTH (units 有り)
            _pair('ddf54429', 56),      # BROW (units 有り)
            _pair('extra_face', 1200),  # 顔サイズだが units 無し → 除外
            _pair('garbage', 12000),    # ゴミ (units 無し) → 除外
        ]
        units_map = {'def7af36': 'BODY', '63f702ce': 'EYES',
                     '6192fe1c': 'MOUTH', 'ddf54429': 'BROW'}
        out = hs.select_import_pairs(pairs, units_map)
        self.assertEqual([p['vb0'] for p in out],
                         ['def7af36', '63f702ce', '6192fe1c', 'ddf54429'])

    def test_units_map_excludes_unregistered_largest(self):
        # units 非空時は units キー一致のみ。units に無い最大ペア
        # (Noelle 911ff708 相当のゴミダンプ) は保険なしで除外される
        pairs = [
            _pair('911ff708', 104857),  # ゴミ (最大・units 無し) → 除外
            _pair('def7af36', 15965),   # ボディ (units 有り)
            _pair('63f702ce', 1083),    # EYES (units 有り)
            _pair('6192fe1c', 877),     # MOUTH (units 有り)
            _pair('ddf54429', 56),      # BROW (units 有り)
        ]
        units_map = {'def7af36': 'BODY', '63f702ce': 'EYES',
                     '6192fe1c': 'MOUTH', 'ddf54429': 'BROW'}
        out = hs.select_import_pairs(pairs, units_map)
        self.assertEqual([p['vb0'] for p in out],
                         ['def7af36', '63f702ce', '6192fe1c', 'ddf54429'])

    def test_units_map_empty_falls_back_to_legacy(self):
        # units_map が空/None なら従来挙動 (ゴミ除外 + 最大 + 顔サイズ)
        pairs = [
            _pair('911ff708', 104857),  # ゴミ
            _pair('def7af36', 15965),   # ボディ
            _pair('63f702ce', 1083),    # EYES
        ]
        expected = ['def7af36', '63f702ce']
        self.assertEqual([p['vb0'] for p in hs.select_import_pairs(pairs, {})],
                         expected)
        self.assertEqual([p['vb0'] for p in hs.select_import_pairs(pairs, None)],
                         expected)


class HeadCenterTest(unittest.TestCase):

    def test_nan_verts_filtered(self):
        # NaN 頂点は除外され、有限頂点のみで計算される
        verts = [(0.0, 0.0, 10.0), (float('nan'), 1.0, 2.0), (1.0, 1.0, 11.0)]
        c = hs.head_center_from_verts(verts)
        self.assertIsNotNone(c)
        self.assertEqual(c, (0.5, 0.5, 10.5))

    def test_all_nan_returns_none(self):
        verts = [(float('nan'), 0.0, 1.0), (float('inf'), 1.0, 2.0)]
        self.assertIsNone(hs.head_center_from_verts(verts))

    def test_empty_returns_none(self):
        self.assertIsNone(hs.head_center_from_verts([]))

    def test_normal_verts(self):
        # fraction=1.0 なら全頂点の中心 (x=(0+1+2)/3, y 同様, z=(0+2+4)/3)
        verts = [(0.0, 0.0, 0.0), (1.0, 1.0, 2.0), (2.0, 2.0, 4.0)]
        c = hs.head_center_from_verts(verts, fraction=1.0)
        self.assertIsNotNone(c)
        self.assertEqual(c, (1.0, 1.0, 2.0))


if __name__ == '__main__':
    unittest.main()
