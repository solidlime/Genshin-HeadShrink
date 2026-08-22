"""T016: dump dir 再オープン時の unit リストリセット廃止のテスト。

- 同一キャラで dump_dir を再設定 → units_list 保持
- 別キャラ名の dir に変更 → units_list クリア + char_name 更新
- 起動時復元フラグ (_restoring_prefs) 中の更新 → クリアされない

Run: python -m pytest scripts/test_t016_dump_dir_reopen.py -q
"""
import os
import sys
import tempfile
import types
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import bpy_teststub  # noqa: E402

sys.modules.setdefault('bpy', bpy_teststub.bpy)


def setUpModule():
    bpy_teststub.reset()


import headshrink_addon as hs  # noqa: E402


class _Unit:
    def __init__(self, vb0):
        self.vb0 = vb0


class _UnitList(list):
    """units_list の Fake (clear() + index 代入を備える)。"""

    def clear(self):
        del self[:]


def _make_props(char_name, units=('6192fe1c', '63f702ce')):
    props = types.SimpleNamespace(
        dump_dir='', char_name=char_name,
        units_list=_UnitList([_Unit(v) for v in units]),
        units_list_index=1)
    return props


def _call_dump_dir_changed(props, char_dir):
    """_dump_dir_changed を Fake bpy で実行する。"""
    saved = (hs.bpy.path.abspath, hs._dump_dir_update, hs._save_prefs)
    hs.bpy.path.abspath = lambda p: p
    hs._dump_dir_update = lambda *a: None
    hs._save_prefs = lambda *a: None
    try:
        props.dump_dir = char_dir
        context = types.SimpleNamespace(
            scene=types.SimpleNamespace(headshrink_props=props))
        hs._dump_dir_changed(props, context)
    finally:
        (hs.bpy.path.abspath, hs._dump_dir_update, hs._save_prefs) = saved


class DumpDirReopenTest(unittest.TestCase):
    def test_same_char_reopen_keeps_units(self):
        d = tempfile.mkdtemp()
        char_dir = os.path.join(d, 'Noelle')
        os.mkdir(char_dir)
        props = _make_props('Noelle')
        _call_dump_dir_changed(props, char_dir)
        # 同一キャラ再オープン: リストは保持される
        self.assertEqual(len(props.units_list), 2)
        self.assertEqual(props.char_name, 'Noelle')
        self.assertEqual(props.units_list_index, 1)

    def test_char_switch_clears_units(self):
        d = tempfile.mkdtemp()
        char_dir = os.path.join(d, 'Mona')
        os.mkdir(char_dir)
        props = _make_props('Noelle')
        _call_dump_dir_changed(props, char_dir)
        # キャラ切替: 従来どおりクリア + char_name 更新 + index リセット
        self.assertEqual(len(props.units_list), 0)
        self.assertEqual(props.char_name, 'Mona')
        self.assertEqual(props.units_list_index, 0)

    def test_restoring_prefs_flag_skips_clear(self):
        d = tempfile.mkdtemp()
        char_dir = os.path.join(d, 'Mona')
        os.mkdir(char_dir)
        props = _make_props('Noelle')
        saved_flag = hs._restoring_prefs
        hs._restoring_prefs = True
        try:
            _call_dump_dir_changed(props, char_dir)
        finally:
            hs._restoring_prefs = saved_flag
        # 復元中: キャラが違っても units は保持される
        self.assertEqual(len(props.units_list), 2)
        self.assertEqual(hs._restoring_prefs, saved_flag)

    def test_register_restore_resets_flag_on_exception(self):
        # register() の復元は try/finally でフラグを必ず戻す
        saved = (hs.load_global_dirs, hs.bpy.utils.register_class,
                 hs.bpy.props.PointerProperty)
        had_types = hasattr(hs.bpy, 'types')
        saved_types = getattr(hs.bpy, 'types', None)
        had_prefs = hasattr(hs.bpy.context, 'preferences')
        saved_prefs = getattr(hs.bpy.context, 'preferences', None)
        hs.load_global_dirs = lambda: (
            r'G:\Dump\Noelle', None, None)

        class _Prefs:
            dump_dir = ''

        prefs = _Prefs()

        def _set_dump_dir(value):
            raise RuntimeError('update callback boom')

        type(prefs).dump_dir = property(
            lambda self: '', _set_dump_dir)
        hs.bpy.utils.register_class = lambda cls: None
        hs.bpy.props.PointerProperty = lambda **k: None
        hs.bpy.types = types.SimpleNamespace(Scene=types.SimpleNamespace())
        hs.bpy.context.preferences = types.SimpleNamespace(
            addons={hs.__name__: prefs})
        try:
            hs.register()
            self.assertFalse(hs._restoring_prefs)
        finally:
            (hs.load_global_dirs, hs.bpy.utils.register_class,
             hs.bpy.props.PointerProperty) = saved
            if had_types:
                hs.bpy.types = saved_types
            else:
                del hs.bpy.types
            if had_prefs:
                hs.bpy.context.preferences = saved_prefs
            else:
                del hs.bpy.context.preferences


if __name__ == '__main__':
    unittest.main(verbosity=2)
