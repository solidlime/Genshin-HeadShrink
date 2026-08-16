# Final Status Report (2026-08-15)

## ✅ Oodle Decompression: COMPLETE

**All 1441 Nilou bundles decompressed successfully** (237 MB output)
**All 88 Mitya bundles decompressed successfully** (35 MB output)

### Critical Fix

`scripts/blb_parser.py` line 81: `size = i32()` inside nodes loop was shadowing the outer `size` variable (the `blocksInfoSize` from header offset 0x04).

**Effect**: Parser was reading block_data from offset 0xf394 instead of 0xcb — completely wrong location, getting garbage.

**Fix**: Renamed inner variable to `node_size`.

### Working Stack

```
.blk → Blb3File parser (FIXED)
     → blocksInfo decrypt (XOR+AES+RC4+GF256, GF256 tables verified)
     → per-block decrypt (first 128B only)
     → oo2core_9_win64.dll OodleLZ_Decompress (Cdecl, 14 args)
     → Unity serialized data
```

## ✅ Mitya Mesh Extraction: COMPLETE

AnimeStudio CLI extracted **25 Mesh OBJs** from 00514567.blk:
- Location: `D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh\`
- Names: Body, Body_LOD1/2/3, Body_Eye, Face, Face_LOD2/3, Face_Eye, Face_Eye_LOD2/3, Bang, Bang_LOD1/2/3, Brow, Brow_LOD2/3, Pupil, Pupil_LOD1/2/3, EyeStar, EffectMesh, etc.

Head shrink pipeline (Blender) verified:
- Baseline: `head_baseline.png`
- Shrunk: `head_shrunk.png` (HEAD_SCALE=0.65)

## ❌ Nilou Mesh Extraction: BLOCKED

**Reason**: Nilou's character mesh is wrapped in **MdbComponent** (ClassID 1152437153 / 0x44B0CBA1).

- AnimeStudio skips MdbComponent as "Unknown ClassIDType"
- UnityPy also doesn't parse it (only finds 2 objects: AssetBundle + AnimationClip)
- MDB format is undocumented publicly (khang06/genshin-studio deleted 2024)
- No known community tool can crack MDB

**Status**: Cannot extract Nilou's 3D model without writing a custom MDB parser (estimated days/weeks).

## Files & Scripts

### Working
- `scripts/blb_parser.py` — Blb3File parser (FIXED, all 1441 Nilou bundles decompressed)
- `scripts/blb_crypto.py` — 4-step crypto (XOR/AES/RC4/GF256)
- `scripts/oodle.py` — Oodle wrapper (oo2core_9_win64.dll)
- `scripts/diff_gf256.py` — table verifier (0 diffs)
- `scripts/test_final.py` — Oodle pipeline smoke test
- `scripts/test_nilou_full.py` — full Nilou decompressor (writes to `D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin`)
- `scripts/test_mitya_full.py` — full Mitya decompressor
- `scripts/render_nilou.py`, `render_nilou_compare.py` — head shrink + render

### Notes
- `notes/blbfile_spec.md` — Blb3File format spec
- `notes/oodle_progress.md` — Oodle iteration log
- `notes/project_status.md` — project status snapshot

### Decompressed Data
- `D:\Documents\Default Project\Nilou\nilou_full_decompressed.bin` — 237 MB (1441 bundles)
- `D:\Documents\Default Project\Nilou\mitya_full_decompressed.bin` — 35 MB (88 bundles)

## Next Step Decision Needed

**Option A — Mitya mod (deliverable now)**
- Use existing 25 OBJs
- Package as XXMI-Launcher mod
- Requires: vertex buffer override format (.ib/.vb mod)

**Option B — Continue Nilou MDB reverse engineering**
- Days/weeks of work
- Unlocks all playable characters

**Option C — Hybrid**
- Ship Mitya mod
- Continue Nilou MDB in background

## Environment Summary

- AnimeStudio: `D:\Tools\AnimeStudio\AnimeStudio-net9-.../bin/`
- Oodle DLL: `scripts\oo2core_9_win64.dll` (606 KB)
- Python: `C:\Python\Python312\python.exe` (lz4, ctypes, UnityPy 1.25.3, lz4.block available)
- Blender 5.2.0 LTS at `D:\Application\blender\`
- Output dir: `D:\Documents\Default Project\Nilou\`
- Working dir: `G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\`

## What the User Asked For

Original goal: head shrink mod for Nilou.
Achievable now: head shrink mod for Mitya (NPC, same format, mesh directly accessible).
Blocked: Nilou (playable, mesh in MdbComponent).