"""test_auto_detect_vertex_range.py — unit tests for auto_detect_vertex_range.

Run:  python test_auto_detect_vertex_range.py
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from auto_detect_vertex_range import (  # noqa: E402
    parse_log,
    cluster_draws,
    auto_detect,
    build_spec,
)

SCRIPT_DIR = Path(__file__).resolve().parent
MIZUKI_LOG = Path(r'G:\XXMI-Launcher-Portable\Mods\mizuki\log.txt')


def make_log(draws, vb_hashes=None, ib_hash='abcd1234'):
    """Build a synthetic 3DMigoto log text.

    draws: list of (count, start_index, base_vertex)
    vb_hashes: parallel list of vb0 hash per draw (defaults to '11111111').
    """
    vb_hashes = vb_hashes or ['11111111'] * len(draws)
    L = ['analyse_options: 0000063d']
    for i, (count, mfi, bvl) in enumerate(draws):
        vb = vb_hashes[i].ljust(8, '1')
        L.append(f'000001 Map(pResource:0xAAAA, Subresource:0, MapType:4, MapFlags:0, pMappedResource:0xBBBB) hash={vb}')
        L.append(f'000001 IASetVertexBuffers(StartSlot:0, NumBuffers:1, ppVertexBuffers:0xCCCC, pStrides:0xDDDD, pOffsets:0xEEEE)')
        L.append(f'       0: resource=0xFFFF hash={vb}')
        L.append(f'000001 IASetIndexBuffer(pIndexBuffer:0x1111, Format:57, Offset:0) hash={ib_hash}')
        L.append(f'000001 DrawIndexed(IndexCount:{count}, StartIndexLocation:{mfi}, BaseVertexLocation:{bvl})')
        L.append(f'000001 3DMigoto pre {{')
    return '\n'.join(L)


class TestParseLog(unittest.TestCase):
    def test_parse_indexed_only(self):
        txt = make_log([(100, 0, 0), (50, 100, 0)])
        draws = parse_log(txt)
        self.assertEqual(len(draws), 2)
        d0 = draws[0]
        self.assertEqual(d0['count'], 100)
        self.assertEqual(d0['start_index'], 0)
        self.assertEqual(d0['base_vertex'], 0)
        self.assertEqual(d0['vb0'], '11111111')
        self.assertEqual(d0['ib'], 'abcd1234')

    def test_parse_skips_non_indexed_draw(self):
        txt = make_log([(100, 0, 0)]) + '\n000002 Draw(VertexCount:99, StartVertexLocation:0)\n'
        draws = parse_log(txt)
        self.assertEqual(len(draws), 1)

    def test_parse_multiple_vb0(self):
        txt = make_log([(10, 0, 0), (20, 0, 0)], vb_hashes=['aa111111', 'bb222222'])
        draws = parse_log(txt)
        self.assertEqual([d['vb0'] for d in draws], ['aa111111', 'bb222222'])


class TestCluster(unittest.TestCase):
    def test_same_vb0_merges(self):
        txt = make_log([(100, 0, 0), (50, 100, 0)], vb_hashes=['11111111', '11111111'])
        groups = cluster_draws(parse_log(txt))
        self.assertEqual(list(groups.keys()), ['Part_11111111'])
        self.assertEqual(len(groups['Part_11111111']), 2)

    def test_diff_vb0_split(self):
        txt = make_log([(100, 0, 0), (50, 100, 0)], vb_hashes=['11111111', '22222222'])
        groups = cluster_draws(parse_log(txt))
        self.assertEqual(list(groups.keys()), ['Part_11111111', 'Part_22222222'])
        self.assertEqual(len(groups['Part_11111111']), 1)
        self.assertEqual(len(groups['Part_22222222']), 1)


class TestInferRanges(unittest.TestCase):
    def test_cumulative_vertex_ranges(self):
        """Case1: two draws -> vertex [0,100]/[100,150], ib [0,100]/[100,150]."""
        txt = make_log([(100, 0, 0), (50, 100, 0)], vb_hashes=['11111111', '22222222'])
        groups = cluster_draws(parse_log(txt))
        spec = build_spec(groups)
        self.assertEqual(spec['vert_count'], 150)
        g0, g1 = spec['groups']
        self.assertEqual(g0['name'], 'Part_11111111')
        self.assertEqual(g0['vertex_range'], [0, 100])
        self.assertEqual(g0['ib_range'], [0, 100])
        self.assertEqual(g1['name'], 'Part_22222222')
        self.assertEqual(g1['vertex_range'], [100, 150])
        self.assertEqual(g1['ib_range'], [100, 150])

    def test_vertex_span_uses_max_base_plus_count(self):
        """BaseVertexLocation shifts vertex span within the group."""
        txt = make_log([(100, 0, 10), (50, 100, 200)], vb_hashes=['11111111', '11111111'])
        groups = cluster_draws(parse_log(txt))
        spec = build_spec(groups)
        g0 = spec['groups'][0]
        # max(bvl+count) = max(110, 250) = 250
        self.assertEqual(g0['vertex_range'][1], 250)
        self.assertEqual(spec['vert_count'], 250)
        # ib range = [min mfi, max mfi+count] = [0, 150]
        self.assertEqual(g0['ib_range'], [0, 150])


class TestAutoDetectFile(unittest.TestCase):
    def test_auto_detect_writes_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / 'log.txt'
            log_path.write_text(
                make_log([(100, 0, 0), (50, 100, 0)],
                         vb_hashes=['11111111', '22222222']),
                encoding='utf-8')
            out = Path(tmp) / 'spec.json'
            spec = auto_detect(str(log_path), output=str(out))
            self.assertEqual(spec['vert_count'], 150)
            self.assertTrue(out.exists())
            loaded = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(loaded['groups'][0]['name'], 'Part_11111111')

    def test_auto_detect_position_buf_sets_vert_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / 'log.txt'
            log_path.write_text(make_log([(100, 0, 0)]), encoding='utf-8')
            pos = Path(tmp) / 'Position.buf'
            pos.write_bytes(b'\x00' * (40 * 300))  # stride 40 x 300 verts
            spec = auto_detect(str(log_path), position_buf_path=str(pos))
            self.assertEqual(spec['vert_count'], 300)


@unittest.skipUnless(MIZUKI_LOG.exists(), 'mizuki log.txt not found')
class TestMizukiRealLog(unittest.TestCase):
    def test_real_log_parses_and_dry_run(self):
        spec = auto_detect(str(MIZUKI_LOG))
        self.assertGreater(len(spec['groups']), 5)
        self.assertGreater(spec['vert_count'], 0)
        # spec must be accepted by build_headshrink_mod.py --dry-run
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / 'spec.json'
            spec_path.write_text(json.dumps(spec), encoding='utf-8')
            r = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / 'build_headshrink_mod.py'),
                 '--char', 'Mizuki', '--dump-dir', str(MIZUKI_LOG.parent),
                 '--output-dir', str(Path(tmp) / 'out'), '--spec', str(spec_path),
                 '--dry-run'],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('Dry run OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
