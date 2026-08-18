"""Unit tests for the units UI (hash direct entry) operators.

Covers: vb0 hash validation / normalization in NHS_OT_UnitsAdd, list
add/update/remove, and the save/load round-trip against face_offsets.json
(units must survive a save -> load cycle without touching other config keys
or face-offset entries).

Run: python test_units_ui.py
"""
import json
import os
import shutil
import sys
import tempfile
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
        def __init__(self):
            self._reports = []

        def report(self, level, msg):
            self._reports.append((set(level), msg))

    props = types.SimpleNamespace(
        StringProperty=_prop_fn, FloatVectorProperty=_prop_fn,
        EnumProperty=_prop_fn, PointerProperty=_prop_fn,
        CollectionProperty=_prop_fn, PropertyGroup=_Base,
        FloatProperty=_prop_fn, BoolProperty=_prop_fn,
        IntProperty=_prop_fn,
    )

    bpy_stub.props = props
    bpy_stub.types = types.SimpleNamespace(
        PropertyGroup=_Base, Operator=_Base, Panel=_Base, UIList=_Base,
        AddonPreferences=_Base)
    bpy_stub.utils = types.SimpleNamespace(
        register_class=lambda c: None, unregister_class=lambda c: None)
    bpy_stub.path = types.SimpleNamespace(abspath=lambda p: p)
    bpy_stub.data = types.SimpleNamespace(
        objects=[],
        collections={},
    )
    bpy_stub.app = types.SimpleNamespace(
        timers=types.SimpleNamespace(register=lambda fn, **kw: None))
    bpy_stub.context = types.SimpleNamespace()
    sys.modules['bpy'] = bpy_stub

import headshrink_addon as hs  # noqa: E402


class _UnitItem:
    def __init__(self, vb0="", role="OTHER"):
        self.vb0 = vb0
        self.role = role


class _UnitList:
    """CollectionProperty モック: add/remove/clear/len/iter/index."""

    def __init__(self):
        self._items = []

    def add(self):
        item = _UnitItem()
        self._items.append(item)
        return item

    def remove(self, i):
        del self._items[i]

    def clear(self):
        self._items = []

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, i):
        return self._items[i]


class _DumpPairItem:
    def __init__(self, pair_name="", vb0="", ib="", vert_count=0):
        self.pair_name = pair_name
        self.vb0 = vb0
        self.ib = ib
        self.vert_count = vert_count


class _DumpPairList:
    """CollectionProperty モック (dump_pairs UIList 用)。"""

    def __init__(self):
        self._items = []

    def add(self):
        item = _DumpPairItem()
        self._items.append(item)
        return item

    def remove(self, i):
        del self._items[i]

    def clear(self):
        self._items = []

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, i):
        return self._items[i]


class _LayoutMock:
    """label() 呼び出しを記録する layout モック (UIList draw_item 検証用)。"""

    def __init__(self):
        self.rows = []
        self.labels = []
        self.icons = []
        self.active = True  # UIList の行アクティブ状態 (未登録ペアは False)

    def row(self):
        r = _LayoutMock()
        self.rows.append(r)
        return r

    def label(self, **kw):
        self.labels.append(kw.get('text'))
        self.icons.append(kw.get('icon'))


def make_props(units=(), dump_pairs=()):
    lst = _UnitList()
    for vb0, role in units:
        item = lst.add()
        item.vb0 = vb0
        item.role = role
    plist = _DumpPairList()
    for pair_name, vb0, ib, vert_count in dump_pairs:
        item = plist.add()
        item.pair_name = pair_name
        item.vb0 = vb0
        item.ib = ib
        item.vert_count = vert_count
    return types.SimpleNamespace(
        units_vb0="", units_role="BODY", units_list=lst,
        units_list_index=0, char_name="TestChar",
        dump_pair="NONE",
        dump_pairs=plist, dump_pairs_index=0,
    )


def make_ctx(props):
    prefs = types.SimpleNamespace(dump_dir="", output_dir="")
    return types.SimpleNamespace(
        scene=types.SimpleNamespace(headshrink_props=props),
        preferences=types.SimpleNamespace(
            addons={hs.__name__: types.SimpleNamespace(preferences=prefs)}))


def run_op(cls, ctx):
    op = cls()
    result = op.execute(ctx)
    return op, result


def make_config_file(units=None, extra=None, char_name='TestChar'):
    """face_offsets.json 用の一時ファイルを作成してパスを返す。"""
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    cfg = {}
    if extra:
        cfg.update(extra)
    if units is not None:
        cfg['units'] = units
    entry = {'__config__': cfg}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({char_name: entry}, f, indent=2, ensure_ascii=False)
    return path


class UnitsAddTest(unittest.TestCase):
    def setUp(self):
        self.props = make_props()
        self.ctx = make_ctx(self.props)

    def test_valid_hash_added(self):
        self.props.units_vb0 = "def7af36"
        op, result = run_op(hs.NHS_OT_UnitsAdd, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(len(self.props.units_list), 1)
        self.assertEqual(self.props.units_list[0].vb0, "def7af36")
        self.assertEqual(self.props.units_list[0].role, "BODY")
        self.assertEqual(self.props.units_vb0, "")  # 入力クリア
        self.assertEqual(self.props.units_list_index, 0)
        self.assertTrue(op._reports and 'INFO' in op._reports[0][0])

    def test_uppercase_normalized(self):
        self.props.units_vb0 = "DEF7AF36"
        run_op(hs.NHS_OT_UnitsAdd, self.ctx)
        self.assertEqual(self.props.units_list[0].vb0, "def7af36")

    def test_invalid_hash_rejected(self):
        for bad in ("xyz", "1234567", "123456789", "", "def7af3g", "def7af3"):
            self.props.units_vb0 = bad
            op, result = run_op(hs.NHS_OT_UnitsAdd, self.ctx)
            self.assertEqual(result, {'CANCELLED'}, f"accepted {bad!r}")
            self.assertTrue(op._reports and 'ERROR' in op._reports[0][0],
                            f"no ERROR for {bad!r}")
            self.assertEqual(len(self.props.units_list), 0)
        # 無効でも units_vb0 は残る (ユーザーが修正できるように)
        self.assertEqual(self.props.units_vb0, "def7af3")

    def test_duplicate_updates_role(self):
        self.props.units_vb0 = "def7af36"
        run_op(hs.NHS_OT_UnitsAdd, self.ctx)
        self.props.units_vb0 = "def7af36"
        self.props.units_role = "OTHER"
        op, result = run_op(hs.NHS_OT_UnitsAdd, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(len(self.props.units_list), 1)
        self.assertEqual(self.props.units_list[0].role, "OTHER")
        self.assertEqual(self.props.units_list_index, 0)


class UnitsRemoveTest(unittest.TestCase):
    def test_remove_selected(self):
        props = make_props(units=[("def7af36", "BODY"), ("63f702ce", "EYES")])
        props.units_list_index = 0
        ctx = make_ctx(props)
        op, result = run_op(hs.NHS_OT_UnitsRemove, ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(len(props.units_list), 1)
        self.assertEqual(props.units_list[0].vb0, "63f702ce")

    def test_remove_last_index_clamped(self):
        props = make_props(units=[("def7af36", "BODY"), ("63f702ce", "EYES")])
        props.units_list_index = 1
        ctx = make_ctx(props)
        run_op(hs.NHS_OT_UnitsRemove, ctx)
        self.assertEqual(len(props.units_list), 1)
        self.assertEqual(props.units_list_index, 0)

    def test_remove_empty_rejected(self):
        props = make_props()
        ctx = make_ctx(props)
        op, result = run_op(hs.NHS_OT_UnitsRemove, ctx)
        self.assertEqual(result, {'CANCELLED'})


class UnitsAddPairTest(unittest.TestCase):
    """NHS_OT_UnitsAddPair: 選択 UIList (dump_pairs) の vb0 を units に登録。"""

    def setUp(self):
        self._orig_pairs = hs._dump_cache['pairs']
        hs._dump_cache['pairs'] = [
            {"vb0": "def7af36", "ib": "aabbccdd", "frame": 0,
             "vert_count": 15965, "index_count": 30000,
             "vb0_path": "x.vb0", "ib_path": "y.ib"},
            {"vb0": "63f702ce", "ib": "11223344", "frame": 0,
             "vert_count": 1083, "index_count": 2000,
             "vb0_path": "x.vb0", "ib_path": "y.ib"},
        ]
        self.props = make_props(dump_pairs=[
            ("def7af36 | aabbccdd", "def7af36", "aabbccdd", 15965),
            ("63f702ce | 11223344", "63f702ce", "11223344", 1083),
        ])
        self.ctx = make_ctx(self.props)

    def tearDown(self):
        hs._dump_cache['pairs'] = self._orig_pairs

    def test_pair_registered(self):
        self.props.dump_pairs_index = 0
        op, result = run_op(hs.NHS_OT_UnitsAddPair, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(len(self.props.units_list), 1)
        self.assertEqual(self.props.units_list[0].vb0, "def7af36")
        self.assertEqual(self.props.units_list[0].role, "BODY")
        self.assertEqual(self.props.units_list_index, 0)
        self.assertTrue(op._reports and 'INFO' in op._reports[0][0])

    def test_empty_list_rejected(self):
        # 未解析 (dump_pairs 空)
        self.props.dump_pairs.clear()
        op, result = run_op(hs.NHS_OT_UnitsAddPair, self.ctx)
        self.assertEqual(result, {'CANCELLED'})
        self.assertEqual(len(self.props.units_list), 0)
        self.assertTrue(op._reports and 'ERROR' in op._reports[0][0])

    def test_index_out_of_range_rejected(self):
        self.props.dump_pairs_index = 99
        op, result = run_op(hs.NHS_OT_UnitsAddPair, self.ctx)
        self.assertEqual(result, {'CANCELLED'})
        self.assertEqual(len(self.props.units_list), 0)
        self.assertTrue(op._reports and 'ERROR' in op._reports[0][0])

    def test_second_pair_registered(self):
        self.props.dump_pairs_index = 1
        op, result = run_op(hs.NHS_OT_UnitsAddPair, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(len(self.props.units_list), 1)
        self.assertEqual(self.props.units_list[0].vb0, "63f702ce")

    def test_duplicate_updates_role(self):
        self.props.dump_pairs_index = 0
        run_op(hs.NHS_OT_UnitsAddPair, self.ctx)
        self.props.units_role = "OTHER"
        op, result = run_op(hs.NHS_OT_UnitsAddPair, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(len(self.props.units_list), 1)
        self.assertEqual(self.props.units_list[0].role, "OTHER")
        self.assertEqual(self.props.units_list_index, 0)


class PreviewPairTest(unittest.TestCase):
    """NHS_OT_PreviewPair: 選択ペアの即プレビュー表示 (index ベース)。"""

    def setUp(self):
        self._orig_pairs = hs._dump_cache['pairs']
        hs._dump_cache['pairs'] = [
            {"vb0": "def7af36", "ib": "aabbccdd", "frame": 0,
             "vert_count": 15965, "index_count": 30000,
             "vb0_path": "x.vb0", "ib_path": "y.ib"},
        ]
        self._orig_import = hs._import_pair
        self._orig_preview = hs._preview_setup_impl
        self._orig_path_fn = hs.face_offsets_path
        self._orig_last = hs._last_preview_pair
        self.path = make_config_file(units={"def7af36": "BODY"})
        hs.face_offsets_path = lambda: self.path
        self.props = make_props(dump_pairs=[
            ("def7af36 | aabbccdd", "def7af36", "aabbccdd", 15965),
        ])
        self.ctx = make_ctx(self.props)

    def tearDown(self):
        hs._dump_cache['pairs'] = self._orig_pairs
        hs._import_pair = self._orig_import
        hs._preview_setup_impl = self._orig_preview
        hs.face_offsets_path = self._orig_path_fn
        hs._last_preview_pair = self._orig_last
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_empty_list_rejected(self):
        # 未解析 (dump_pairs 空)
        self.props.dump_pairs.clear()
        op, result = run_op(hs.NHS_OT_PreviewPair, self.ctx)
        self.assertEqual(result, {'CANCELLED'})
        self.assertTrue(op._reports and 'ERROR' in op._reports[0][0])

    def test_index_out_of_range_rejected(self):
        self.props.dump_pairs_index = 99
        op, result = run_op(hs.NHS_OT_PreviewPair, self.ctx)
        self.assertEqual(result, {'CANCELLED'})
        self.assertTrue(op._reports and 'ERROR' in op._reports[0][0])

    def test_pair_not_in_cache_rejected(self):
        # 選択ペアが _dump_cache に無い (解析後の入れ替え等)
        hs._dump_cache['pairs'] = [
            {"vb0": "99999999", "ib": "12345678", "frame": 0,
             "vert_count": 1, "index_count": 1,
             "vb0_path": "x.vb0", "ib_path": "y.ib"},
        ]
        op, result = run_op(hs.NHS_OT_PreviewPair, self.ctx)
        self.assertEqual(result, {'CANCELLED'})
        self.assertTrue(op._reports and 'ERROR' in op._reports[0][0])

    def test_pair_previewed(self):
        # 正常系: 選択ペアがインポートされプレビュー配置される
        imported = []

        def fake_import_pair(context, pair, units_map=None):
            imported.append(pair)
            return ("OBJ", "BODY", pair['vert_count'], 1, "MESH")

        hs._import_pair = fake_import_pair
        hs._preview_setup_impl = lambda self_, context: {'FINISHED'}
        self.props.dump_pairs_index = 0
        op, result = run_op(hs.NHS_OT_PreviewPair, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]['vb0'], "def7af36")
        self.assertTrue(op._reports and 'INFO' in op._reports[0][0])


class HasRegisteredUnitsTest(unittest.TestCase):
    """_has_registered_units: units 登録済み判定 (dump_dir 変更時の自動発火条件)。"""

    def setUp(self):
        self._orig_path_fn = hs.face_offsets_path
        self.path = make_config_file(units={"def7af36": "BODY"})
        hs.face_offsets_path = lambda: self.path

    def tearDown(self):
        hs.face_offsets_path = self._orig_path_fn
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_registered_returns_true(self):
        self.assertTrue(hs._has_registered_units("TestChar"))

    def test_no_units_key_returns_false(self):
        # units キー自体が無いキャラ
        path = make_config_file(units=None)
        try:
            hs.face_offsets_path = lambda: path
            self.assertFalse(hs._has_registered_units("TestChar"))
        finally:
            hs.face_offsets_path = self._orig_path_fn
            os.unlink(path)

    def test_empty_units_returns_false(self):
        # units キーはあるが空 dict
        with open(self.path, encoding='utf-8') as f:
            data = json.load(f)
        data['TestChar']['__config__']['units'] = {}
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.assertFalse(hs._has_registered_units("TestChar"))

    def test_unsaved_char_returns_false(self):
        # 未保存キャラ (config エントリ無し)
        self.assertFalse(hs._has_registered_units("OtherChar"))


class UnitsListDrawTest(unittest.TestCase):
    """HS_UL_UnitsList.draw_item が vb0 / role を layout に書き出すこと。"""

    def _draw(self, item, layout_type='DEFAULT'):
        ul = hs.HS_UL_UnitsList()
        ul.layout_type = layout_type
        layout = _LayoutMock()
        ul.draw_item(None, layout, None, item, 0, None, 'units_list', 0)
        return layout

    def test_draw_item_shows_vb0_and_role(self):
        props = make_props(units=[('def7af36', 'BODY')])
        layout = self._draw(props.units_list[0])
        self.assertEqual(layout.rows[0].labels, ['def7af36', 'BODY'])

    def test_draw_item_shows_other_role_too(self):
        props = make_props(units=[('ddf54429', 'OTHER')])
        layout = self._draw(props.units_list[0], layout_type='COMPACT')
        self.assertEqual(layout.rows[0].labels, ['ddf54429', 'OTHER'])

    def test_draw_item_non_visible_layout_skips(self):
        # 'GRID' 等の表示対象外 layout では何も描画しない
        props = make_props(units=[('63f702ce', 'EYES')])
        ul = hs.HS_UL_UnitsList()
        ul.layout_type = 'GRID'
        layout = _LayoutMock()
        ul.draw_item(None, layout, None, props.units_list[0], 0,
                     None, 'units_list', 0)
        self.assertEqual(layout.rows, [])
        self.assertEqual(layout.labels, [])


class AnalyzeDumpSyncTest(unittest.TestCase):
    """NHS_OT_AnalyzeDump: 解析結果が dump_pairs UIList に同期されること。"""

    def setUp(self):
        self._orig_scan = hs.scan_dump_dir
        self._orig_abspath = hs.bpy.path.abspath
        self._orig_pairs = hs._dump_cache['pairs']
        self._tmpdir = tempfile.mkdtemp()
        hs.bpy.path.abspath = lambda p: p
        self.props = make_props()
        self.ctx = make_ctx(self.props)
        self.ctx.preferences.addons[hs.__name__].preferences.dump_dir = \
            self._tmpdir

    def tearDown(self):
        hs.scan_dump_dir = self._orig_scan
        hs.bpy.path.abspath = self._orig_abspath
        hs._dump_cache['pairs'] = self._orig_pairs
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_pairs_synced_to_dump_pairs(self):
        hs.scan_dump_dir = lambda d: [
            {"vb0": "def7af36", "ib": "aabbccdd", "frame": 0,
             "vert_count": 15965, "index_count": 30000,
             "vb0_path": "x.vb0", "ib_path": "y.ib"},
            {"vb0": "63f702ce", "ib": "11223344", "frame": 0,
             "vert_count": 1083, "index_count": 2000,
             "vb0_path": "x.vb0", "ib_path": "y.ib"},
        ]
        op, result = run_op(hs.NHS_OT_AnalyzeDump, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(len(self.props.dump_pairs), 2)
        self.assertEqual(self.props.dump_pairs[0].vb0, "def7af36")
        self.assertEqual(self.props.dump_pairs[0].ib, "aabbccdd")
        self.assertEqual(self.props.dump_pairs[0].pair_name,
                         "def7af36 | aabbccdd")
        self.assertEqual(self.props.dump_pairs[0].vert_count, 15965)
        self.assertEqual(self.props.dump_pairs[1].vb0, "63f702ce")

    def test_cleared_when_no_pairs(self):
        hs.scan_dump_dir = lambda d: []
        run_op(hs.NHS_OT_AnalyzeDump, self.ctx)
        self.assertEqual(len(self.props.dump_pairs), 0)


class DumpPairsIndexUpdateTest(unittest.TestCase):
    """_dump_pairs_index_update: 選択変更で preview_pair がスケジュールされる。"""

    def setUp(self):
        self._orig_last = hs._last_preview_pair
        self._orig_register = hs.bpy.app.timers.register
        self._scheduled = []
        hs.bpy.app.timers.register = (
            lambda fn, **kw: self._scheduled.append((fn, kw)))
        self.props = make_props(dump_pairs=[
            ("def7af36 | aabbccdd", "def7af36", "aabbccdd", 15965),
        ])

    def tearDown(self):
        hs._last_preview_pair = self._orig_last
        hs.bpy.app.timers.register = self._orig_register

    def test_select_schedules_preview(self):
        hs._last_preview_pair = None
        self.props.dump_pairs_index = 0
        hs._dump_pairs_index_update(self.props, None)
        self.assertEqual(len(self._scheduled), 1)
        fn, kw = self._scheduled[0]
        self.assertEqual(kw.get('first_interval'), 0.1)
        # タイマー関数は preview_pair を実行して None (解除) を返す
        self.assertIsNone(fn())

    def test_same_pair_does_not_reschedule(self):
        hs._last_preview_pair = "def7af36|aabbccdd"
        self.props.dump_pairs_index = 0
        hs._dump_pairs_index_update(self.props, None)
        self.assertEqual(self._scheduled, [])

    def test_empty_list_returns(self):
        self.props.dump_pairs.clear()
        self.props.dump_pairs_index = 0
        hs._dump_pairs_index_update(self.props, None)
        self.assertEqual(self._scheduled, [])


class DumpPairListDrawTest(unittest.TestCase):
    """HS_UL_DumpPairList.draw_item がペア名 + 頂点数を表示すること。"""

    def _draw(self, props, item, layout_type='DEFAULT'):
        ul = hs.HS_UL_DumpPairList()
        ul.layout_type = layout_type
        layout = _LayoutMock()
        ctx = make_ctx(props)
        ul.draw_item(ctx, layout, props, item, 0, props,
                     'dump_pairs_index', 0)
        return layout

    def test_draw_item_shows_pair_name_and_verts(self):
        props = make_props(dump_pairs=[
            ("def7af36 | aabbccdd", "def7af36", "aabbccdd", 15965)])
        layout = self._draw(props, props.dump_pairs[0])
        self.assertEqual(layout.rows[0].labels,
                         ['def7af36 | aabbccdd', '15965v'])

    def test_draw_item_non_visible_layout_skips(self):
        props = make_props(dump_pairs=[
            ("63f702ce | 11223344", "63f702ce", "11223344", 1083)])
        ul = hs.HS_UL_DumpPairList()
        ul.layout_type = 'GRID'
        layout = _LayoutMock()
        ctx = make_ctx(props)
        ul.draw_item(ctx, layout, props, props.dump_pairs[0], 0,
                     props, 'dump_pairs_index', 0)
        self.assertEqual(layout.rows, [])
        self.assertEqual(layout.labels, [])

    def test_draw_item_registered_pair_marked(self):
        # units 登録済み vb0 は CHECKBOX_HLT + 行がアクティブのまま
        props = make_props(
            units=[("def7af36", "BODY")],
            dump_pairs=[("def7af36 | aabbccdd", "def7af36", "aabbccdd", 15965)])
        ctx = make_ctx(props)
        ul = hs.HS_UL_DumpPairList()
        ul.layout_type = 'DEFAULT'
        layout = _LayoutMock()
        ul.draw_item(ctx, layout, props, props.dump_pairs[0], 0,
                     props, 'dump_pairs_index', 0)
        self.assertTrue(layout.active)
        self.assertEqual(layout.rows[0].icons, ['CHECKBOX_HLT', None])

    def test_draw_item_unregistered_pair_dimmed(self):
        # units 未登録 vb0 は BLANK1 + 行全体が非アクティブ (薄く表示)
        props = make_props(dump_pairs=[
            ("911ff708 | 11223344", "911ff708", "11223344", 104857)])
        ctx = make_ctx(props)
        ul = hs.HS_UL_DumpPairList()
        ul.layout_type = 'COMPACT'
        layout = _LayoutMock()
        ul.draw_item(ctx, layout, props, props.dump_pairs[0], 0,
                     props, 'dump_pairs_index', 0)
        self.assertFalse(layout.active)
        self.assertEqual(layout.rows[0].icons, ['BLANK1', None])


class LoadConfigTest(unittest.TestCase):
    """NHS_OT_LoadCharConfig / NHS_OT_LoadDefaultConfig の適用テスト。"""

    def setUp(self):
        self._orig_path_fn = hs.face_offsets_path
        self.props = make_props()
        self.props.shrink_scale = 0.5
        self.props.shrink_falloff = 0.3
        self.ctx = make_ctx(self.props)

    def tearDown(self):
        hs.face_offsets_path = self._orig_path_fn

    def test_load_char_config_applies(self):
        path = make_config_file(extra={'shrink_scale': 0.65,
                                       'shrink_falloff': 0.8})
        hs.face_offsets_path = lambda: path
        op, result = run_op(hs.NHS_OT_LoadCharConfig, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(self.props.shrink_scale, 0.65)
        self.assertEqual(self.props.shrink_falloff, 0.8)
        self.assertTrue(op._reports and 'INFO' in op._reports[0][0])
        self.assertIn('Loaded 2 settings for TestChar', op._reports[0][1])

    def test_load_char_config_no_config(self):
        path = make_config_file()  # __config__ 空
        hs.face_offsets_path = lambda: path
        op, result = run_op(hs.NHS_OT_LoadCharConfig, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(self.props.shrink_scale, 0.5)  # 不変
        self.assertIn('No saved config for TestChar', op._reports[0][1])

    def test_load_default_config_applies(self):
        path = make_config_file(extra={'shrink_scale': 0.7},
                                char_name='__default__')
        hs.face_offsets_path = lambda: path
        op, result = run_op(hs.NHS_OT_LoadDefaultConfig, self.ctx)
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(self.props.shrink_scale, 0.7)
        self.assertIn('Loaded 1 default settings', op._reports[0][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
