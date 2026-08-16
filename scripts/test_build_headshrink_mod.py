"""Tests for build_headshrink_mod.py — pure math, no Blender / XXMI deps."""
import math, os, struct, sys, tempfile, unittest
from pathlib import Path

# Make the script importable.
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink\scripts')
from build_headshrink_mod import (
    bbox_center, scale_positions, split_ib, to_r32_ib, render_ini,
)


class TestScalePositions(unittest.TestCase):
    def test_scale_centered_xyz(self):
        # 3 verts, stride 12, all positions distinct
        buf = struct.pack('<3f3f3f', 0.0, 0.0, 0.0,
                                       1.0, 2.0, 3.0,
                                       -1.0, -2.0, -3.0)
        center = bbox_center(buf, 12, [0, 1, 2])
        # center should be (0, 0, 0) symmetric
        self.assertAlmostEqual(center[0], 0.0)
        self.assertAlmostEqual(center[1], 0.0)
        self.assertAlmostEqual(center[2], 0.0)
        out = scale_positions(buf, 12, [0, 1, 2], (0.5, 0.5, 0.5), center)
        x, y, z = struct.unpack_from('<3f', out, 0)
        self.assertAlmostEqual(x, 0.0)
        x, y, z = struct.unpack_from('<3f', out, 12)
        self.assertAlmostEqual(x, 0.5); self.assertAlmostEqual(y, 1.0); self.assertAlmostEqual(z, 1.5)
        x, y, z = struct.unpack_from('<3f', out, 24)
        self.assertAlmostEqual(x, -0.5); self.assertAlmostEqual(y, -1.0); self.assertAlmostEqual(z, -1.5)

    def test_scale_preserves_other_bytes(self):
        # stride 16 (12 xyz + 4 uv pack), make sure bytes 12..16 untouched
        buf = bytearray(16)
        struct.pack_into('<3f', buf, 0, 1.0, 2.0, 3.0)
        buf[12:16] = b'\xAA\xBB\xCC\xDD'
        center = (1.0, 2.0, 3.0)
        out = scale_positions(bytes(buf), 16, [0], (0.5, 0.5, 0.5), center)
        # shouldn't move (already at center)
        x, y, z = struct.unpack_from('<3f', out, 0)
        self.assertAlmostEqual(x, 1.0); self.assertAlmostEqual(y, 2.0); self.assertAlmostEqual(z, 3.0)
        # bytes 12..16 unchanged
        self.assertEqual(out[12:16], b'\xAA\xBB\xCC\xDD')

    def test_uniform_scale_expected_radius(self):
        # head-like point at (0.5, 1.0, 0)
        buf = struct.pack('<3f', 0.5, 1.0, 0.0)
        center = (0.0, 1.0, 0.0)
        out = scale_positions(buf, 12, [0], (0.65, 0.65, 0.65), center)
        x, y, z = struct.unpack('<3f', out)
        self.assertAlmostEqual(x, 0.325, places=4)
        self.assertAlmostEqual(y, 1.0, places=4)
        self.assertAlmostEqual(z, 0.0, places=4)


class TestSplitIb(unittest.TestCase):
    def test_split_two_ranges(self):
        ib = struct.pack('<8I', 0, 1, 2, 3, 4, 5, 6, 7)
        out = split_ib(ib, 4, [('Head', 0, 3), ('Body', 3, 8)])
        self.assertEqual(len(out['Head']), 12)
        self.assertEqual(len(out['Body']), 20)
        self.assertEqual(out['Head'], struct.pack('<3I', 0, 1, 2))
        self.assertEqual(out['Body'], struct.pack('<5I', 3, 4, 5, 6, 7))

    def test_split_uint16(self):
        # Input 16bit -> output always R32_UINT (uint32 per index).
        ib = struct.pack('<6H', 100, 101, 102, 103, 104, 105)
        out = split_ib(ib, 2, [('A', 0, 3), ('B', 3, 6)])
        self.assertEqual(out['A'], struct.pack('<3I', 100, 101, 102))
        self.assertEqual(out['B'], struct.pack('<3I', 103, 104, 105))

    def test_to_r32_16bit(self):
        ib = struct.pack('<4H', 1, 300, 65535, 0)
        self.assertEqual(to_r32_ib(ib, 2),
                         struct.pack('<4I', 1, 300, 65535, 0))

    def test_to_r32_32bit_passthrough(self):
        ib = struct.pack('<3I', 7, 8, 9)
        self.assertIs(to_r32_ib(ib, 4), ib)


class TestRenderIni(unittest.TestCase):
    def test_basic_structure(self):
        hashes = {'position': 'aaaa', 'blend': 'bbbb',
                  'ib': 'cccc', 'texcoord': 'dddd'}
        ini = render_ini('Mona', hashes, 13855, 40, 32, 12,
                         [{'name': 'Head', 'match_first_index': 0, 'count': 17688},
                          {'name': 'Body', 'match_first_index': 17688, 'count': 35814}],
                         has_blend=True, has_texcoord=True)
        # Must reference the 5 mandatory sections.
        for must in ['[TextureOverrideMonaPosition]', '[TextureOverrideMonaBlend]',
                     '[TextureOverrideMonaTexcoord]', '[TextureOverrideMonaIB]',
                     '[TextureOverrideMonaHead]', '[TextureOverrideMonaBody]',
                     '[ResourceMonaPosition]', '[ResourceMonaHeadIB]',
                     '[ResourceMonaBodyIB]']:
            self.assertIn(must, ini)
        # Bennett/XXMI pattern: no VertexLimitRaise, IB override is
        # skip-only, part overrides carry drawindexed = index count.
        self.assertNotIn('VertexLimitRaise', ini)
        self.assertIn('drawindexed = 17688, 0, 0', ini)
        self.assertNotIn('drawindexed = auto', ini)
        self.assertNotIn('[Constants]', ini)
        self.assertNotIn('[Present]', ini)


if __name__ == '__main__':
    unittest.main()
