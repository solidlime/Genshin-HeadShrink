"""DIFF_HLSL 冪等化テスト。

CopyDispatch 用 HLSL の意味論を純 Python シミュレータで検証する。
同一 bind ハッシュに複数キャラのセクションが一致しても Δ が累算しないこと
(冪等性) を保証する。bpy 不要。
"""
import os
import struct
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# --- minimal bpy stub: only needed for class definitions to import ---
import bpy_teststub  # noqa: E402

sys.modules.setdefault('bpy', bpy_teststub.bpy)

import headshrink_addon as hs  # noqa: E402

import re

# テンプレートの #define HS_EPS から自動取得 (テンプレートと模擬器の drift 防止)
EPS = float(re.search(r'#define HS_EPS ([0-9.eE+-]+)',
                      hs.DIFF_HLSL).group(1))


def _f32(v):
    """float32 ラウンドトリップで HLSL 側の精度に揃える。"""
    return struct.unpack('<f', struct.pack('<f', v))[0]


def _dispatch(rw_positions, base_positions, key_positions):
    """DIFF_HLSL main の意味論をシミュレートする。

    cur≈key -> skip / cur≈base -> key 代入 / それ以外 -> 何もしない。
    """
    for i in range(len(rw_positions)):
        cur = tuple(_f32(c) for c in rw_positions[i])
        b = tuple(_f32(c) for c in base_positions[i])
        k = tuple(_f32(c) for c in key_positions[i])
        if _dist(cur, k) < EPS:
            continue
        if _dist(cur, b) < EPS:
            rw_positions[i] = list(k)


def _dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _make_buffers(n=8):
    base = [[_f32(1.0 * i), _f32(0.5 * i), _f32(-0.25 * i)] for i in range(n)]
    key = [[_f32(b[0] + 0.01), _f32(b[1] - 0.02), _f32(b[2] + 0.03)]
           for b in base]
    return [list(b) for b in base], [list(b) for b in key]


def test_single_apply():
    base, key = _make_buffers()
    rw = [list(b) for b in base]
    _dispatch(rw, base, key)
    assert rw == key


def test_double_apply_idempotent():
    base, key = _make_buffers()
    rw = [list(b) for b in base]
    _dispatch(rw, base, key)
    _dispatch(rw, base, key)
    assert rw == key


def test_triple_apply_idempotent():
    base, key = _make_buffers()
    rw = [list(b) for b in base]
    for _ in range(3):
        _dispatch(rw, base, key)
    assert rw == key


def test_variant_within_eps_converges_to_key():
    # T017: cur が base±6e-4 の表情変種 (観測最大差) -> EPS=5e-3 で
    # base と判定され key へ収束する (点滅恒久対応)
    base, key = _make_buffers()
    variant = [[b[0] + 6e-4, b[1] - 6e-4, b[2]] for b in base]
    rw = [list(v) for v in variant]
    _dispatch(rw, base, key)
    assert rw == key


def test_unmatched_state_noop():
    # cur が base でも key でもない (EPS=5e-3 より大きくズレた状態) -> 不変
    base, key = _make_buffers()
    far = [[b[0] + 1e-2, b[1] - 1e-2, b[2]] for b in base]
    rw = [list(v) for v in far]
    _dispatch(rw, base, key)
    assert rw == far


def test_hlsl_template_structure():
    tpl = hs.DIFF_HLSL
    assert 'distance(cur, k)' in tpl
    assert 'distance(cur, b)' in tpl
    assert 'return' in tpl
    assert '+=' not in tpl


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
