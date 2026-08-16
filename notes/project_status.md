# Project Status (2026-08-15)

## 🎉 Oodle Decompression: WORKING

**Milestone**: Full Blb3File → Oodle → Unity serialized data pipeline functional.

### Critical Bug Fixed

`scripts/blb_parser.py` line 81 had `size = i32()` inside the nodes parsing loop, which **shadowed** the outer `size` variable (originally `blocksInfoSize`).

**Effect**: `self.block_data_offset = offset + 0x1C + size` was using the LAST node's size value instead of the actual blocksInfoSize. So parser read block_data from a completely wrong offset, getting garbage that wasn't Oodle data.

**Fix**: Renamed inner variable to `node_size` so the outer `size` remains intact.

### Verification

| File | Bundles | Tested | OK | FAIL |
|---|---|---|---|---|
| Mitya 00514567.blk | 88 | 20 | 20 | 0 |
| Nilou 02050112.blk | 1441 | 20 | 20 | 0 |

Decompressed data first bytes: `8c 06 01 85 83 89 ...` (OodleLZ magic 0x8C confirmed).

### Working DLL

`oo2core_9_win64.dll` (606 KB, RAD Game Tools official) at `scripts/oo2core_9_win64.dll`
- Export: `OodleLZ_Decompress`
- Calling convention: Cdecl (CDLL)
- 14 args: src, srcLen, dst, dstLen, fuzzSafe, checkCRC, verbosity, rawBuf, rawBufSize, callback, cbUser, decMem, decMemSize, threadPhase

### AnimeStudio.Ooz.dll Issue

`AnimeStudio.Ooz.dll` (202 KB, vendored zao/ooz fork) has `Ooz_Decompress` with **15 args** (not 14 as AnimeStudio's C# wrapper declares). Wrong signature → -1 returns. Skip for now.

## Pipeline Status

```
.blk (Blb3File) → blocksInfo decrypt (XOR/AES/RC4/GF256) → block_data offsets
                → per-block decrypt (first 128B only, in-place) → Oodle decompress
                → Unity serialized data (CAB + SerializedFile)
```

## Remaining Blockers

### Nilou-specific: MdbComponent (ClassID 1152437153)

- 02050112.blk Mesh assets are wrapped in MdbComponent containers
- AnimeStudio skips them as "Unknown ClassIDType"
- MDB format is undocumented (khang06/genshin-studio deleted 2024)
- Cannot extract Nilou's character mesh without MDB parser

### Unity Serialized Data Parsing

Even after Oodle decompresses successfully, the output is in Unity CAB format (not UnityFS/Raw/Web). Requires:
- CAB wrapper parser
- Unity SerializedFile parser
- TypeTree handling (miHoYo strips typetree, uses MD5 fingerprints)

**Available tools**: UnityPy 1.25.3 installed (Python lib) — may handle CAB format

## Decision Point

**Option A**: Use Mitya 25 OBJs (already extracted) for head shrink mod demo
- Head shrink pipeline already verified
- Renders exist (head_baseline.png vs head_shrunk.png)
- Mod packaging needed

**Option B**: Continue cracking Nilou's MDB format
- Days/weeks of reverse engineering
- Would enable all playable characters

**Option C**: Hybrid — ship Mitya mod now, continue Nilou in background

## Assets Already Available

- `D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh\` — 25 Mitya OBJs
- `D:\Documents\Default Project\Nilou\render_test\head_baseline.png` — original
- `D:\Documents\Default Project\Nilou\render_test\head_shrunk.png` — shrunk

## Scripts (working)

- `scripts/blb_parser.py` — Blb3File parser (FIXED)
- `scripts/blb_crypto.py` — 4-step decrypt
- `scripts/oodle.py` — Oodle wrapper (needs update to use oo2core path)
- `scripts/diff_gf256.py` — table verifier
- `scripts/test_final.py` — Oodle pipeline test (20/20 OK)
- `scripts/investigate_format.py` — decompressed data inspection
- `scripts/render_nilou.py`, `render_nilou_compare.py` — head shrink + render
- `scripts/parse_blb_header.py` — header dump