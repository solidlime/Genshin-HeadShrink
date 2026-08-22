# -*- coding: utf-8 -*-
"""T018: Sucrose mod の顔 Key.buf 再生成 (Blender background 実行用)。

T015 時点コードで export された Key.buf に face_offset を反映する。
アドオンの実関数 (_face_key_verts / replace_positions / display_to_game)
を流用し、数学は再実装しない。

実行:
  & "D:\Application\blender\blender.exe" --background --python tools\scratch\regen_sucrose_keys.py
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, '..', '..', 'scripts'))
sys.path.insert(0, SCRIPTS)

import headshrink_addon as hs  # noqa: E402

MOD_DIR = r'G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink\Sucrose'
SCALE = 0.9
OFF_DISPLAY = (0.0, -0.003, 0.0)  # face_offset_eye/mouth/brow 共通 (display 空間)
UNITS = ['SucroseMouth', 'SucroseEyes', 'SucroseBrow']
TOL = 1e-4  # float32 再丸め誤差の許容


def main():
    off_game = hs.display_to_game(OFF_DISPLAY)
    stride = hs.DUMP_STRIDE
    print(f'[regen] offset display={OFF_DISPLAY} -> game={off_game}, '
          f'scale={SCALE}, stride={stride}')
    all_ok = True
    for name in UNITS:
        base_p = os.path.join(MOD_DIR, name + 'Base.buf')
        key_p = os.path.join(MOD_DIR, name + 'Key.buf')
        bak_p = key_p + '.bak-T018'
        with open(base_p, 'rb') as f:
            base_bytes = f.read()
        n = len(base_bytes) // stride
        if not os.path.exists(bak_p):
            shutil.copy2(key_p, bak_p)
            print(f'[regen] {name}: backup -> {os.path.basename(bak_p)}')
        with open(bak_p, 'rb') as f:
            old_key = f.read()
        assert len(old_key) == len(base_bytes), name
        # Base.buf の position (game 空間) から Key = f(Base, scale, offset)
        base_verts = [struct.unpack_from('<3f', base_bytes, i * stride)
                      for i in range(n)]
        key_verts = hs._face_key_verts(
            list(base_verts), SCALE, 'UNIFORM', (SCALE,) * 3, off_game)
        new_key = hs.replace_positions(base_bytes, key_verts, stride)
        # 検証1: 新旧 Key 差分 == 一様平行移動ベクトル
        max_err = 0.0
        for i in range(n):
            o = struct.unpack_from('<3f', old_key, i * stride)
            w = struct.unpack_from('<3f', new_key, i * stride)
            for j in range(3):
                max_err = max(max_err, abs((w[j] - o[j]) - off_game[j]))
        # 検証2: normal/tangent 領域 (bytes 12..stride) は非変更
        normals_ok = all(
            new_key[i * stride + 12:(i + 1) * stride]
            == old_key[i * stride + 12:(i + 1) * stride]
            for i in range(n))
        ok = max_err <= TOL and normals_ok
        all_ok &= ok
        print(f'[regen] {name}: verts={n} delta_match='
              f'{max_err <= TOL} (max_err={max_err:.3e}) '
              f'normal_tangent_unchanged={normals_ok}')
        if not ok:
            print(f'[regen] {name}: VERIFICATION FAILED - not written')
            continue
        with open(key_p, 'wb') as f:
            f.write(new_key)
        print(f'[regen] {name}: written {key_p}')
    print('[regen] RESULT:', 'OK' if all_ok else 'FAILED')
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
