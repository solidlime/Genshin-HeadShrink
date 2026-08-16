"""Unit + e2e tests for units-based multi-buffer mod building.

Covers: 16bit IB (R16_UINT) / 32bit IB (R32_UINT) switch, multiple units,
frame-dump direct loading (vb0=/ib= filename hash resolution), per-unit
blend/texcoord, ib-less (scale-only) units, alias fallback, --scale across
all units, and legacy single-unit spec compat.
"""
import json
import math
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))
import build_headshrink_mod as b  # noqa: E402

STRIDE = 40


def make_vb(n):
    """n verts, stride 40: xyz = (v, 2v, 3v) as float32, rest zeroed."""
    out = bytearray()
    for v in range(n):
        out += struct.pack('<3f', float(v), float(v * 2), float(v * 3))
        out += b'\x00' * (STRIDE - 12)
    return bytes(out)


def make_ib(indices, index_bytes):
    return b''.join(
        struct.pack('<H' if index_bytes == 2 else '<I', i) for i in indices)


def frame_name(kind, h, frame='000037'):
    return f'{frame}-{kind}={h}-vs=0000000000000000-ps=0000000000000000.buf'


def run_cli(args_list, cwd):
    res = subprocess.run(
        [sys.executable, str(SCRIPTS / 'build_headshrink_mod.py')] + args_list,
        capture_output=True, text=True, cwd=cwd)
    return res


class RenderIniTest(unittest.TestCase):
    def test_units_sections(self):
        ini = b.render_ini(
            'TestBody', {'position': 'def7af36', 'ib': '9cf0789e'},
            15965, 40, 32, 12,
            [{'name': 'Head', 'match_first_index': 0, 'count': 5},
             {'name': 'Body', 'match_first_index': 5, 'count': 10}],
            False, False)
        for needle in [
            '[TextureOverrideTestBodyPosition]',
            'hash = def7af36',
            'vb0 = ResourceTestBodyPosition',
            '[TextureOverrideTestBodyIB]',
            'hash = 9cf0789e',
            'handling = skip',
            '[TextureOverrideTestBodyHead]',
            'match_first_index = 0',
            'ib = ResourceTestBodyHeadIB',
            'drawindexed = 5, 0, 0',
            '[TextureOverrideTestBodyBody]',
            'match_first_index = 5',
            'drawindexed = 10, 0, 0',
            '[ResourceTestBodyHeadIB]',
            'format = DXGI_FORMAT_R32_UINT',
            'filename = TestBodyHead.ib',
            '[ResourceTestBodyBodyIB]',
            'format = DXGI_FORMAT_R32_UINT',
        ]:
            self.assertIn(needle, ini)
        # Bennett pattern: no VertexLimitRaise / drawindexed=auto;
        # [Constants]/[Present] are emitted once per .ini by the caller.
        self.assertNotIn('VertexLimitRaise', ini)
        self.assertNotIn('drawindexed = auto', ini)
        self.assertNotIn('[Constants]', ini)
        self.assertNotIn('[Present]', ini)

    def test_r32_default(self):
        ini = b.render_ini(
            'Test', {'position': 'a', 'ib': 'b'},
            10, 40, 32, 12,
            [{'name': 'Head', 'match_first_index': 0, 'count': 5}],
            False, False)
        self.assertIn('format = DXGI_FORMAT_R32_UINT', ini)

    def test_blend_texcoord_sections(self):
        ini = b.render_ini(
            'TestEyes', {'position': '63f702ce', 'ib': '0bcb587f',
                         'blend': 'b043715a', 'texcoord': '4f12ab88'},
            1083, 40, 32, 12,
            [{'name': 'Head', 'match_first_index': 0, 'count': 5}],
            True, True)
        for needle in [
            '[TextureOverrideTestEyesBlend]',
            'hash = b043715a',
            'handling = skip',
            'vb1 = ResourceTestEyesBlend',
            '[TextureOverrideTestEyesTexcoord]',
            'hash = 4f12ab88',
            'vb1 = ResourceTestEyesTexcoord',
            '[ResourceTestEyesBlend]',
            'stride = 32',
            'filename = TestEyesBlend.buf',
            '[ResourceTestEyesTexcoord]',
            'stride = 12',
            'filename = TestEyesTexcoord.buf',
        ]:
            self.assertIn(needle, ini)
        # draw=N,0 is a non-indexed Draw() that corrupts rendering
        # (3DMigoto CommandList.cpp:1206) — must not be emitted.
        self.assertNotIn('draw = 1083, 0', ini)

    def test_has_ib_false_omits_ib_sections(self):
        ini = b.render_ini(
            'TestEyes', {'position': '63f702ce'},
            1083, 40, 32, 12,
            [{'name': 'Head', 'match_first_index': 0, 'count': 5}],
            False, False, has_ib=False)
        self.assertIn('[TextureOverrideTestEyesPosition]', ini)
        for needle in ['[TextureOverrideTestEyesIB]',
                       '[TextureOverrideTestEyesHead]',
                       '[ResourceTestEyesHeadIB]']:
            self.assertNotIn(needle, ini)


class FindDumpHashTest(unittest.TestCase):
    def test_finds_vb0_and_ib_by_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / frame_name('vb0', 'def7af36')).write_bytes(b'POS')
            (d / frame_name('ib', '9cf0789e')).write_bytes(b'IB')
            pos = b.find_dump_hash(d, 'vb0=', 'def7af36')
            ib = b.find_dump_hash(d, 'ib=', '9cf0789e')
            self.assertIsNotNone(pos)
            self.assertIsNotNone(ib)
            self.assertEqual(pos.name, frame_name('vb0', 'def7af36'))
            self.assertEqual(ib.name, frame_name('ib', '9cf0789e'))

    def test_missing_hash_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / frame_name('vb0', 'def7af36')).write_bytes(b'POS')
            self.assertIsNone(b.find_dump_hash(d, 'vb0=', 'deadbeef'))
            self.assertIsNone(b.find_dump_hash(d, 'ib=', 'deadbeef'))


class UnitsCliTest(unittest.TestCase):
    """e2e: 2 units, 16bit IB, --scale applied to all units, frame dump input."""

    UNITS = [
        {'name': 'Body', 'position': 'def7af36', 'ib': '9cf0789e',
         'vert_count': 15,
         'groups': [
             {'name': 'Head', 'vertex_range': [0, 5], 'ib_range': [0, 5]},
             {'name': 'Body', 'vertex_range': [5, 15], 'ib_range': [5, 15]},
         ]},
        {'name': 'Eyes', 'position': '63f702ce', 'ib': '0bcb587f',
         'vert_count': 5,
         'groups': [
             {'name': 'Head', 'vertex_range': [0, 5], 'ib_range': [0, 5]},
         ]},
    ]

    def _write_frame_dump(self, d, index_bytes):
        (d / frame_name('vb0', 'def7af36')).write_bytes(make_vb(15))
        (d / frame_name('ib', '9cf0789e')).write_bytes(
            make_ib(list(range(15)), index_bytes))
        (d / frame_name('vb0', '63f702ce')).write_bytes(make_vb(5))
        (d / frame_name('ib', '0bcb587f')).write_bytes(
            make_ib(list(range(5)), index_bytes))

    def _write_spec(self, d, spec):
        (d / 'spec.json').write_text(json.dumps(spec, indent=2))

    def _read_xyz(self, buf, v, stride=STRIDE):
        return struct.unpack_from('<3f', buf, v * stride)

    def test_16bit_two_units_scale_and_ib(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dump, out = d / 'dump', d / 'out'
            dump.mkdir(); out.mkdir()
            self._write_frame_dump(dump, 2)
            spec = {'index_bytes': 2, 'units': self.UNITS}
            self._write_spec(d, spec)

            res = run_cli([
                '--char', 'Noe', '--dump-dir', str(dump),
                '--output-dir', str(out), '--spec', str(d / 'spec.json'),
                '--scale', 'Head=0.65,0.65,0.65',
            ], d)
            self.assertEqual(res.returncode, 0, res.stderr)

            # Unit Body: Head verts 0..4 scaled, Body verts 5..14 untouched.
            body_pos = (out / 'NoeBodyPosition.buf').read_bytes()
            cx = (0.0 + 4.0) / 2  # x bbox center of verts 0..4
            self.assertAlmostEqual(self._read_xyz(body_pos, 0)[0],
                                   cx + (0.0 - cx) * 0.65, places=4)
            self.assertAlmostEqual(self._read_xyz(body_pos, 4)[0],
                                   cx + (4.0 - cx) * 0.65, places=4)
            x5 = self._read_xyz(body_pos, 5)[0]
            self.assertEqual(x5, 5.0)  # outside Head range -> untouched

            # Unit Eyes: all verts scaled (only Head group).
            eyes_pos = (out / 'NoeEyesPosition.buf').read_bytes()
            ecx = (0.0 + 4.0) / 2
            self.assertAlmostEqual(self._read_xyz(eyes_pos, 0)[0],
                                   ecx + (0.0 - ecx) * 0.65, places=4)
            self.assertAlmostEqual(self._read_xyz(eyes_pos, 4)[0],
                                   ecx + (4.0 - ecx) * 0.65, places=4)

            # IB split: input is 16bit, output is always R32 (index*4 bytes).
            self.assertEqual((out / 'NoeBodyHead.ib').read_bytes(),
                             make_ib(list(range(5)), 4))
            self.assertEqual((out / 'NoeBodyBody.ib').read_bytes(),
                             make_ib(list(range(5, 15)), 4))
            self.assertEqual((out / 'NoeEyesHead.ib').read_bytes(),
                             make_ib(list(range(5)), 4))

            # .ini: per-unit sections + R32 format (Bennett pattern).
            ini = (out / 'Noe.ini').read_text(encoding='utf-8')
            for needle in [
                '[TextureOverrideNoeBodyPosition]',
                'hash = def7af36',
                'vb0 = ResourceNoeBodyPosition',
                '[TextureOverrideNoeBodyIB]',
                'hash = 9cf0789e',
                'handling = skip',
                '[TextureOverrideNoeBodyHead]',
                'match_first_index = 0',
                'ib = ResourceNoeBodyHeadIB',
                'drawindexed = 5, 0, 0',
                '[TextureOverrideNoeBodyBody]',
                'match_first_index = 5',
                'drawindexed = 10, 0, 0',
                '[TextureOverrideNoeEyesPosition]',
                'hash = 63f702ce',
                '[ResourceNoeBodyHeadIB]',
                'format = DXGI_FORMAT_R32_UINT',
                'filename = NoeBodyHead.ib',
            ]:
                self.assertIn(needle, ini)
            # One [Constants] at top, one [Present] post at bottom, no
            # VertexLimitRaise / drawindexed=auto.
            self.assertEqual(ini.count('[Constants]'), 1)
            self.assertEqual(ini.count('[Present]'), 1)
            self.assertLess(ini.index('[Constants]'),
                            ini.index('[TextureOverrideNoeBodyPosition]'))
            self.assertLess(ini.index('[TextureOverrideNoeEyesHead]'),
                            ini.index('[Present]'))
            self.assertIn('post $active = 0', ini)
            self.assertNotIn('VertexLimitRaise', ini)
            self.assertNotIn('drawindexed = auto', ini)

    def test_index_bytes_defaults_to_args_value(self):
        # Spec omits index_bytes -> --index-bytes (default 4) must win -> R32.
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dump, out = d / 'dump', d / 'out'
            dump.mkdir(); out.mkdir()
            self._write_frame_dump(dump, 4)
            spec = {'units': self.UNITS}  # no index_bytes key
            self._write_spec(d, spec)

            res = run_cli([
                '--char', 'Noe', '--dump-dir', str(dump),
                '--output-dir', str(out), '--spec', str(d / 'spec.json'),
            ], d)
            self.assertEqual(res.returncode, 0, res.stderr)
            ini = (out / 'Noe.ini').read_text(encoding='utf-8')
            self.assertIn('format = DXGI_FORMAT_R32_UINT', ini)
            # 4-byte index slices.
            ib = make_ib(list(range(15)), 4)
            self.assertEqual((out / 'NoeBodyHead.ib').read_bytes(),
                             ib[:5 * 4])

    def test_blend_texcoord_per_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dump, out = d / 'dump', d / 'out'
            dump.mkdir(); out.mkdir()
            self._write_frame_dump(dump, 2)
            (dump / frame_name('vb1', 'b043715a')).write_bytes(
                b'\x01' * (32 * 5))
            (dump / frame_name('vb2', '4f12ab88')).write_bytes(
                b'\x02' * (12 * 5))
            units = [dict(self.UNITS[1], blend='b043715a',
                          texcoord='4f12ab88')]
            self._write_spec(d, {'index_bytes': 2, 'units': units})

            res = run_cli([
                '--char', 'Noe', '--dump-dir', str(dump),
                '--output-dir', str(out), '--spec', str(d / 'spec.json'),
            ], d)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual((out / 'NoeEyesBlend.buf').read_bytes(),
                             b'\x01' * (32 * 5))
            self.assertEqual((out / 'NoeEyesTexcoord.buf').read_bytes(),
                             b'\x02' * (12 * 5))
            ini = (out / 'Noe.ini').read_text(encoding='utf-8')
            for needle in [
                '[TextureOverrideNoeEyesBlend]',
                'hash = b043715a',
                '[TextureOverrideNoeEyesTexcoord]',
                'hash = 4f12ab88',
                '[ResourceNoeEyesBlend]',
                'stride = 32',
                'filename = NoeEyesBlend.buf',
                '[ResourceNoeEyesTexcoord]',
                'stride = 12',
            ]:
                self.assertIn(needle, ini)
            # draw=N,0 non-indexed Draw() must not be emitted for Blend.
            self.assertNotIn('draw = 5, 0', ini)
            self.assertNotIn('draw = 15, 0', ini)

    def test_per_unit_blend_stride(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dump, out = d / 'dump', d / 'out'
            dump.mkdir(); out.mkdir()
            self._write_frame_dump(dump, 2)
            (dump / frame_name('vb1', '8f1eff2c')).write_bytes(
                b'\x01' * (20 * 15))
            (dump / frame_name('vb1', 'a51badce')).write_bytes(
                b'\x01' * (12 * 5))
            units = [
                dict(self.UNITS[0], blend='8f1eff2c', blend_stride=20),
                dict(self.UNITS[1], blend='a51badce', blend_stride=12),
            ]
            self._write_spec(d, {'index_bytes': 2, 'units': units})

            res = run_cli([
                '--char', 'Noe', '--dump-dir', str(dump),
                '--output-dir', str(out), '--spec', str(d / 'spec.json'),
            ], d)
            self.assertEqual(res.returncode, 0, res.stderr)
            ini = (out / 'Noe.ini').read_text(encoding='utf-8')
            self.assertIn('[ResourceNoeBodyBlend]\n'
                          'type = Buffer\n'
                          'stride = 20', ini)
            self.assertIn('[ResourceNoeEyesBlend]\n'
                          'type = Buffer\n'
                          'stride = 12', ini)

    def test_ib_less_scale_only_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dump, out = d / 'dump', d / 'out'
            dump.mkdir(); out.mkdir()
            (dump / frame_name('vb0', 'ddf54429')).write_bytes(make_vb(5))
            units = [{'name': 'Brow', 'position': 'ddf54429',
                      'vert_count': 5,
                      'groups': [{'name': 'Head',
                                  'vertex_range': [0, 5],
                                  'ib_range': [0, 5]}]}]
            self._write_spec(d, {'index_bytes': 2, 'units': units})

            res = run_cli([
                '--char', 'Noe', '--dump-dir', str(dump),
                '--output-dir', str(out), '--spec', str(d / 'spec.json'),
                '--scale', 'Head=0.5,0.5,0.5',
            ], d)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue((out / 'NoeBrowPosition.buf').exists())
            # No ib in spec -> no .ib files, no IB sections in .ini.
            self.assertFalse((out / 'NoeBrowHead.ib').exists())
            ini = (out / 'Noe.ini').read_text(encoding='utf-8')
            self.assertIn('[TextureOverrideNoeBrowPosition]', ini)
            self.assertNotIn('[TextureOverrideNoeBrowIB]', ini)
            self.assertNotIn('[ResourceNoeBrowHeadIB]', ini)

    def test_alias_fallback_when_no_frame_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dump, out = d / 'dump', d / 'out'
            dump.mkdir(); out.mkdir()
            # Legacy filenames only (no NNNNNN-vb0=/ib= files).
            (dump / 'Position.buf').write_bytes(make_vb(15))
            (dump / 'IB.ib').write_bytes(make_ib(list(range(15)), 2))
            self._write_spec(d, {'index_bytes': 2, 'units': self.UNITS})

            res = run_cli([
                '--char', 'Noe', '--dump-dir', str(dump),
                '--output-dir', str(out), '--spec', str(d / 'spec.json'),
            ], d)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue((out / 'NoeBodyPosition.buf').exists())
            self.assertTrue((out / 'NoeBodyHead.ib').exists())

    def test_old_form_backward_compat(self):
        # Legacy single-unit spec (no 'units' key) still routes to the
        # hash.json + Position.buf/IB.ib path and keeps plain {char} sections.
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dump, out = d / 'dump', d / 'out'
            dump.mkdir(); out.mkdir()
            (dump / 'Position.buf').write_bytes(make_vb(10))
            (dump / 'IB.ib').write_bytes(make_ib(list(range(30)), 4))
            (dump / 'hash.json').write_text(json.dumps({
                'position': '7a1dc890', 'ib': '5b0a37c2',
                'blend': 'b043715a', 'texcoord': '4f12ab88',
                'vertex_limit': '9c8e7f12'}))
            (dump / 'Blend.buf').write_bytes(b'\x00' * (32 * 10))
            (dump / 'TexCoord.buf').write_bytes(b'\x00' * (12 * 10))
            spec = {'vert_count': 10, 'blend_stride': 32,
                    'texcoord_stride': 12,
                    'groups': [
                        {'name': 'Head', 'vertex_range': [0, 5],
                         'ib_range': [0, 15]},
                        {'name': 'Body', 'vertex_range': [5, 10],
                         'ib_range': [15, 30]}]}
            self._write_spec(d, spec)

            res = run_cli([
                '--char', 'Synth', '--dump-dir', str(dump),
                '--output-dir', str(out), '--spec', str(d / 'spec.json'),
                '--scale', 'Head=0.5', '--index-bytes', '4',
            ], d)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue((out / 'SynthPosition.buf').exists())
            ini = (out / 'Synth.ini').read_text(encoding='utf-8')
            self.assertIn('[TextureOverrideSynthPosition]', ini)
            self.assertIn('format = DXGI_FORMAT_R32_UINT', ini)
            self.assertIn('hash = 7a1dc890', ini)


if __name__ == '__main__':
    unittest.main()
