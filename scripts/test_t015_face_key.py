"""T015: 共有顔ハッシュ Key 正規化 + IB ゲートのテスト。

- 顔 UI ユニット (EYES/MOUTH/BROW) の Key は f(Base, scale) の純スケール
  (配置移動なし)。プレビュー配置が変わっても Key.buf バイト不変。
- IB ハッシュセクション (handling=skip) に $is = 1 を含む。
- 本体 (BODY) / 非顔ユニットは従来通り配置移動が反映される (回帰ガード)。

Run: python -m pytest scripts/test_t015_face_key.py -q
"""
import os
import struct
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


def _base_verts(n):
    """テスト用 Base (display空間): v_i = (i, 2i, 3i)。"""
    return [(float(i), 2.0 * i, 3.0 * i) for i in range(n)]


class _Attr:
    def __init__(self, flat):
        self._flat = flat
        self.data = types.SimpleNamespace(
            foreach_get=lambda name, dest, _f=self._flat:
                dest.__setitem__(slice(None), _f))


class _Mesh:
    def __init__(self, base, co_list):
        n = len(base)
        flat = [c for v in base for c in v]
        self.vertices = [types.SimpleNamespace(co=list(c)) for c in co_list]
        self._attr = _Attr(flat)

    @property
    def attributes(self):
        return self

    def get(self, name):
        return self._attr if name == 'hs_original_pos' else None


class _Obj:
    def __init__(self, name, vb0, role, mesh):
        self.type = 'MESH'
        self.name = name
        self.data = mesh
        self._props = {'hs_vb0_hash': vb0, 'hs_role': role}

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __getitem__(self, key):
        return self._props[key]


def _run_export(objs, scale=0.65, face_offsets=None):
    """ExportDiff.execute を Fake bpy で実行し、出力ディレクトリを返す。"""
    tmp = tempfile.mkdtemp()
    coll = types.SimpleNamespace(objects=objs)
    saved_data_collections = getattr(hs.bpy.data, 'collections', None)
    hs.bpy.data.collections = types.SimpleNamespace(
        get=lambda name: coll if name == 'HS_Preview' else None)
    saved = (hs.bpy.path.abspath, hs._clean_export_dir,
             hs._find_face_diffuse_hash, hs.auto_extra_hashes,
             hs._dump_cache)
    hs.bpy.path.abspath = lambda p: p
    hs._clean_export_dir = lambda *a, **k: 0
    hs._find_face_diffuse_hash = lambda *a: None
    hs.auto_extra_hashes = lambda *a, **k: {}
    hs._dump_cache = {}
    try:
        props = types.SimpleNamespace(
            char_name='Noelle', position_vs=hs.DEFAULT_POSITION_VS,
            shrink_scale=scale, shrink_scale_mode='UNIFORM',
            shrink_scale_xyz=(0.95, 0.95, 0.95))
        for k, v in (face_offsets or {}).items():
            setattr(props, k, v)
        context = types.SimpleNamespace(
            scene=types.SimpleNamespace(headshrink_props=props),
            preferences=types.SimpleNamespace(addons={
                hs.__name__: types.SimpleNamespace(
                    preferences=types.SimpleNamespace(output_dir=tmp))}))
        op = types.SimpleNamespace(report=lambda level, msg: None)
        result = hs.NHS_OT_ExportDiff.execute(op, context)
    finally:
        (hs.bpy.path.abspath, hs._clean_export_dir,
         hs._find_face_diffuse_hash, hs.auto_extra_hashes,
         hs._dump_cache) = saved
        if saved_data_collections is None:
            try:
                delattr(hs.bpy.data, 'collections')
            except AttributeError:
                pass
        else:
            hs.bpy.data.collections = saved_data_collections
    assert result == {'FINISHED'}, result
    return os.path.join(tmp, 'Noelle')


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def _positions(buf, n, stride=hs.DUMP_STRIDE):
    return [struct.unpack_from('<3f', buf, i * stride) for i in range(n)]


class FaceKeyNormalizationTest(unittest.TestCase):
    """T015(a): 顔 UI ユニットの Key = f(Base, scale) 純スケール。"""

    def test_key_translation_invariant(self):
        # 配置 (preview の v.co オフセット) が変わっても Key/Base はバイト不変
        base = _base_verts(8)
        run_a = _run_export([_Obj(
            'Mouth1', '6192fe1c', 'MOUTH',
            _Mesh(base, [(x + 10.0, y + 5.0, z - 3.0) for x, y, z in base]))])
        run_b = _run_export([_Obj(
            'Mouth1', '6192fe1c', 'MOUTH',
            _Mesh(base, [(x - 7.5, y + 1.25, z + 9.0) for x, y, z in base]))])
        for fn in ('NoelleMouthKey.buf', 'NoelleMouthBase.buf'):
            self.assertEqual(_read(os.path.join(run_a, fn)),
                             _read(os.path.join(run_b, fn)), fn)

    def test_key_is_pure_scale_of_base(self):
        base = _base_verts(6)
        out = _run_export([_Obj(
            'Eyes1', '63f702ce', 'EYES',
            _Mesh(base, [(x + 4.0, y, z) for x, y, z in base]))], scale=0.5)
        base_buf = _read(os.path.join(out, 'NoelleEyesBase.buf'))
        key_buf = _read(os.path.join(out, 'NoelleEyesKey.buf'))
        self.assertNotEqual(base_buf, key_buf)
        expected = hs.replace_positions(
            base_buf,
            hs._face_key_verts([hs.display_to_game(v) for v in base],
                               0.5, 'UNIFORM', (0.95, 0.95, 0.95)),
            hs.DUMP_STRIDE)
        self.assertEqual(key_buf, expected)

    def test_key_scale_one_identity(self):
        # scale=1.0 なら Key == Base (変形なし)。符号ゼロ (-0.0 vs 0.0) は
        # 数値的に同一なので float 比較する
        base = _base_verts(5)
        out = _run_export([_Obj(
            'Brow1', 'ddf54429', 'BROW',
            _Mesh(base, [(x + 3.0, y, z) for x, y, z in base]))], scale=1.0)
        key = _positions(_read(os.path.join(out, 'NoelleBrowKey.buf')), 5)
        base_p = _positions(_read(os.path.join(out, 'NoelleBrowBase.buf')), 5)
        self.assertEqual(key, base_p)

    def test_key_offset_translation(self):
        # T018: face_offset (display 空間) は game 空間へ変換されて Key に
        # 加算される。scale=1.0 + offset なら Key = Base + display_to_game(off)
        base = _base_verts(6)
        off = (1.5, -2.0, 3.0)
        out = _run_export(
            [_Obj('Mouth1', '6192fe1c', 'MOUTH',
                  _Mesh(base, [(x + 4.0, y, z) for x, y, z in base]))],
            scale=1.0,
            face_offsets={'face_offset_mouth': off})
        key = _positions(_read(os.path.join(out, 'NoelleMouthKey.buf')), 6)
        off_game = hs.display_to_game(off)
        for got, b in zip(key, base):
            bg = hs.display_to_game(b)
            for i in range(3):
                self.assertAlmostEqual(got[i], bg[i] + off_game[i], places=5)

    def test_ini_ib_sections_emit_is_gate(self):
        # T015(b): IB ハッシュセクション (handling=skip) は毎ドロー発火の
        # $is = 1 を持つ。BodyGate セクションも残置 (フォールバック)。
        units = [
            {'name': 'NoelleBody', 'vb_hash': 'e36be83b',
             'position_hash': 'bbdaf598', 'vert_count': 100, 'role': 'BODY',
             'ib': '9cf0789e', 'ib_splits': [(0, 50), (50, 50)]},
            {'name': 'NoelleMouth', 'vb_hash': '6192fe1c',
             'vert_count': 10, 'role': 'MOUTH'},
        ]
        ini = hs.build_diff_ini('Noelle', units, 'VB_REPLACE', None, None,
                                None, 'e36be83b',
                                {'9cf0789e': [(0, 50), (50, 50)]})
        ib_block = ini.split('[TextureOverrideNoelleIB]', 1)[1]
        ib_block = ib_block.split('[TextureOverride', 1)[0]
        self.assertIn('handling = skip', ib_block)
        self.assertIn('$is = 1', ib_block)
        self.assertIn('[TextureOverrideBodyGate]', ini)
        # fallback パス (_ini_ib_split_overrides) も同様
        fallback = hs._ini_ib_split_overrides(
            'Noelle', {'911ff708': [(0, 10), (10, 5)]}, set())
        self.assertIn('$is = 1', '\n'.join(fallback))


class NonFaceUnitRegressionTest(unittest.TestCase):
    """T015 回帰ガード: 非顔/BODY ユニットは従来通り配置が反映される。"""

    def test_other_role_key_reflects_placement(self):
        # role OTHER (delta path) は preview 配置が Key に反映される
        base = _base_verts(4)
        delta = [(1.0, -2.0, 3.0)] * 4
        out = _run_export([_Obj(
            'Other1', '99998888', 'OTHER',
            _Mesh(base, [(x + d[0], y + d[1], z + d[2])
                         for (x, y, z), d in zip(base, delta)]))])
        # role OTHER は Unit<hash8> 名にフォールバックする
        key = _positions(_read(os.path.join(out, 'NoelleUnit99998888Key.buf')), 4)
        expected = [hs.display_to_game((v[0] + d[0], v[1] + d[1], v[2] + d[2]))
                    for v, d in zip(base, delta)]
        for got, exp in zip(key, expected):
            for g, e in zip(got, exp):
                self.assertAlmostEqual(g, e, places=5)

    def test_body_position_reflects_placement(self):
        # BODY (VB_REPLACE) は Position.buf = f(preview v.co)。配置移動が反映
        base = _base_verts(4)
        dump_bytes = bytes(range(4 * hs.DUMP_STRIDE))
        fake_dump = os.path.join(tempfile.mkdtemp(), 'fake.buf')
        with open(fake_dump, 'wb') as f:
            f.write(dump_bytes)
        saved_fpv = hs.find_position_vb
        hs.find_position_vb = lambda *a, **k: {
            'path': fake_dump, 'vert_count': 4, 'vs': '', 'vb_hash': 'bbdaf598'}
        try:
            out_a = _run_export([_Obj(
                'Body1', 'def7af36', 'BODY',
                _Mesh(base, [(x + 10.0, y, z) for x, y, z in base]))])
            out_b = _run_export([_Obj(
                'Body1', 'def7af36', 'BODY',
                _Mesh(base, [(x - 5.0, y, z) for x, y, z in base]))])
        finally:
            hs.find_position_vb = saved_fpv
        pos_a = _read(os.path.join(out_a, 'NoelleBodyPosition.buf'))
        pos_b = _read(os.path.join(out_b, 'NoelleBodyPosition.buf'))
        self.assertNotEqual(pos_a, pos_b)
        pv = [hs.display_to_position_vb((x + 10.0, y, z)) for x, y, z in base]
        self.assertEqual(pos_a, hs.build_position_buf(dump_bytes, pv))


if __name__ == '__main__':
    unittest.main(verbosity=2)

