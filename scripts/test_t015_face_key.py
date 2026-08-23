"""T015〜T020: 顔 Key 正規化・IB ゲート・スタンドアロン顔override廃止のテスト。

- _face_key_verts の数学 (純スケール + offset、T018)。T020 で export 経路は
  廃止されたが純関数は資産として残置。
- IB ハッシュセクション (handling=skip) は $is を立てない (T019:
  キャラ間共有ハッシュでの cross-char 汚染防止)。
- T020: 顔 UI ロールのセクション/buf は生成されない。BODY/OTHER は従来通り。

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
    """T015/T018: _face_key_verts の数学 (純関数テスト)。

    T020 でスタンドアロン顔override生成は廃止されたが、純関数は資産として
    残置するため直接検証する。
    """

    def test_key_is_pure_scale_of_base(self):
        base = [hs.display_to_game(v) for v in _base_verts(6)]
        key = hs._face_key_verts(base, 0.5, 'UNIFORM', (0.95, 0.95, 0.95))
        mins = [min(v[i] for v in base) for i in range(3)]
        maxs = [max(v[i] for v in base) for i in range(3)]
        c = [(mins[i] + maxs[i]) / 2.0 for i in range(3)]
        for got, b in zip(key, base):
            for i in range(3):
                self.assertAlmostEqual(got[i], c[i] + (b[i] - c[i]) * 0.5,
                                       places=6)

    def test_key_scale_one_identity(self):
        # scale=1.0 なら Key == Base (変形なし)
        base = [hs.display_to_game(v) for v in _base_verts(5)]
        key = hs._face_key_verts(base, 1.0, 'UNIFORM', (0.95, 0.95, 0.95))
        for got, b in zip(key, base):
            for i in range(3):
                self.assertAlmostEqual(got[i], b[i], places=6)

    def test_key_offset_translation(self):
        # T018: offset はスケール後に加算される (呼び出し側で game 空間に
        # 変換済みのこと)。scale=1.0 + offset なら Key = Base + offset
        base = [hs.display_to_game(v) for v in _base_verts(6)]
        off = (1.5, -2.0, 3.0)
        key = hs._face_key_verts(base, 1.0, 'UNIFORM', (0.95,) * 3, off)
        for got, b in zip(key, base):
            for i in range(3):
                self.assertAlmostEqual(got[i], b[i] + off[i], places=6)

    def test_ini_ib_sections_emit_is_gate(self):
        # T019: IB ハッシュセクション (handling=skip) は $is を立てない
        # (IB ハッシュはキャラ間共有 → cross-char 汚染の根因)。
        # BodyGate セクションは残置 (フォールバック)。
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
        self.assertNotIn('$is = 1', ib_block)
        self.assertIn('[TextureOverrideBodyGate]', ini)
        # fallback パス (_ini_ib_split_overrides) も同様
        fallback = hs._ini_ib_split_overrides(
            'Noelle', {'911ff708': [(0, 10), (10, 5)]}, set())
        fb = '\n'.join(fallback)
        self.assertIn('handling = skip', fb)
        self.assertNotIn('$is = 1', fb)


class FaceOverrideDroppedTest(unittest.TestCase):
    """T020: スタンドアロン顔override生成の廃止。

    顔 UI ロール (EYES/MOUTH/BROW) のセクション・buf は生成されず、
    統合メッシュ経路 (BODY/OTHER) は従来通り生成される。
    """

    def test_face_units_not_exported(self):
        base = _base_verts(4)
        objs = [
            _Obj('Mouth1', '6192fe1c', 'MOUTH', _Mesh(base, base)),
            _Obj('Eyes1', '63f702ce', 'EYES', _Mesh(base, base)),
            _Obj('Brow1', 'ddf54429', 'BROW', _Mesh(base, base)),
            _Obj('Other1', '99998888', 'OTHER', _Mesh(base, base)),
        ]
        out = _run_export(objs)
        for fn in ('NoelleMouthBase.buf', 'NoelleMouthKey.buf',
                   'NoelleEyesBase.buf', 'NoelleEyesKey.buf',
                   'NoelleBrowBase.buf', 'NoelleBrowKey.buf'):
            self.assertFalse(os.path.exists(os.path.join(out, fn)), fn)
        ini = open(os.path.join(out, 'Noelle.ini'), encoding='utf-8').read()
        for needle in ('[TextureOverrideNoelleMouth',
                       '[TextureOverrideNoelleEyes',
                       '[TextureOverrideNoelleBrow',
                       'CommandListNoelleMouth',
                       'ResourceNoelleMouthBase'):
            self.assertNotIn(needle, ini)
        # 統合メッシュ経路 (OTHER) は生成され続ける
        self.assertTrue(os.path.exists(
            os.path.join(out, 'NoelleUnit99998888Key.buf')))
        self.assertIn('[TextureOverrideNoelleUnit99998888]', ini)


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

