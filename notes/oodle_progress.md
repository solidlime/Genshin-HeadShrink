# Oodle Decompression Progress Log

**Date**: 2026-08-15
**File**: `02050112.blk` bundle 0 (first bundle)

## Iteration Summary

| # | DLL | Function | Mode | rc | Notes |
|---|---|---|---|---|---|
| 1 | AnimeStudio.Ooz.dll (correct path now) | `Ooz_Decompress` | WinDLL StdCall | -1 | DLL loaded OK, signature OK |
| 2 | oo2core_9_win64.dll | `OodleLZ_Decompress` | CDLL Cdecl | 0 | Fail (full data) |
| 2b | oo2core_9_win64.dll | `OodleLZ_Decompress` | CDLL skip6 | 0 | Fail (after 6B skip) |
| 3 | oo2core_9_win64.dll | `OodleLZ_Decompress` | WinDLL StdCall | 0 | Fail (full data) |

## All paths return failure — input data is NOT valid Oodle

Decrypted block0 first 16 bytes: `53 aa ec 15 f1 fe f9 84 1f 54 b0 c9 32 73 b2 f9`

**Expected Oodle magic: 0x8C** — NOT present!

## Possible Causes

1. **Wrong bundle** — 02050112.blk has 1441 bundles. Previous test parsed bundle 0 (offset 0). Maybe Oodle-compressed data is in different bundle.
2. **Parser misalignment** — Blb3File parser may be reading wrong offsets, producing wrong compressed_size.
3. **Decryption bug** — Despite GF256 tables matching, the 4-step crypto may apply incorrectly for this bundle.
4. **Unknown inner format** — block_data might have additional header wrapping.

## Verification Commands Needed

1. Dump raw pre-decrypt first 16 bytes — see if the encrypted form looks random (good) or has structure
2. Compare `compressed_size = 99721` vs b16's `61708` — different bundle?
3. Try other bundles in 02050112.blk — iterate to find one that decrypts to 0x8C magic
4. Check if `block_data_offset` calculation is correct

## Parsed Values (02050112.blk bundle 0)

| Field | Value | Note |
|---|---|---|
| uncompressed_size (1<<shift) | 99924 | shift=16.666? |
| blocks_info_count | 1 | |
| block0.compressed_size | 99721 | **Mismatch with b16's 61708** |
| block0.uncompressed_size | 124036 | last_uncompressed |
| block0.flags | 0x9 | = Oodle (compression_type=9 stored as flags) |
| decrypted[0:6] | `53 aa ec 15 f1 fe` | NOT Oodle magic |
| decrypted[6:16] | `f9 84 1f 54 b0 c9 32 73 b2 f9` | NOT Oodle magic |

## Test Scripts

- `scripts/test_oodle_v3.py` — current comprehensive test (4 patterns)
- `scripts/test_oodle_v2.py` — previous version
- `scripts/test_oodle.py` — original

## 🎉 **ROOT CAUSE FOUND + FIXED**

**Bug**: `scripts/blb_parser.py` line 81 had `size = i32()` inside nodes loop, which **shadowed** the outer `size` variable (the `blocksInfoSize` at offset 0x04 of header).

This caused:
- `self.block_data_offset = offset + 0x1C + size` to use the LAST node's `size` value (e.g., 62,328 = 0xf378)
- Instead of the actual blocksInfoSize (175)
- So parser read block_data from WRONG offset (0xf394 vs 0xcb) — getting garbage instead of real Oodle data

**Fix**: Renamed inner variable to `node_size`.

```python
# Before:
for i in range(nodes_count):
    offset_v = i32()
    size = i32()  # ← shadows outer `size`!

# After:
for i in range(nodes_count):
    offset_v = i32()
    node_size = i32()  # ← no shadow
```

## Final Verification (2026-08-15, post-fix)

**Mitya 00514567.blk** (88 bundles): **20/20 OK** (first 20 tested)
**Nilou 02050112.blk** (1441 bundles): **20/20 OK** (first 20 tested)

Decrypted block0 first 16 bytes (post-fix): `8c 06 01 85 83 89 85 81 00 00 00 7d 00 00 f1 0c` ← **0x8C = OodleLZ magic confirmed**

Oodle decompression returns exact `uncompressed_size` bytes (rc=124036, rc=262144, etc.)

## Working DLL

- `oo2core_9_win64.dll` (606 KB) — works perfectly with `OodleLZ_Decompress` (14 args, Cdecl CDLL)
- Located at `scripts/oo2core_9_win64.dll`

## Next Steps

1. Decompress ALL 1441 bundles in 02050112.blk
2. Parse Unity serialized file format from decompressed data
3. Find Nilou's Mesh/SkinnedMeshRenderer assets (ClassID 43)
4. Extract and render