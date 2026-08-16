# Blb3File Format Spec (Genshin .blk)

**Date**: 2026-08-15
**Source**: AnimeStudio/BlbFile.cs (Escartem master)
**Verified against**: 02050112.blk (1441 bundles), 00514567.blk (Mitya)

## Magic / Dispatcher

- `Blb\x03` (4 bytes) → Blb3File (current Genshin/SR/ZZZ format)
- `AssetsManager.cs:562-565` dispatches Blb3File vs MhyFile based on magic + game type
- Genshin 6.x uses **Blb3File** (not mhy0/mhy1) — confirmed via grep `mhy0` count=0 in 02050112.blk

## Header Layout (32 bytes)

```
Offset  Size  Field
0x00    4     magic = "Blb\x03" (0x03 6C 62 42 LE)
0x04    4     blocksInfoSize  (u32 LE)
0x08    4     unk             (always 0x00000005 in current builds)
0x0C    16    headerKey       (AES key for blocksInfo decrypt)
```

After header: `blocksInfoSize` bytes of **encrypted** blocksInfo → BlbUtils.Decrypt(headerKey, blocksInfo) → 4-step crypto (XOR + AES + RC4 + GF256).

## Decrypted blocksInfo Layout

```
u32   size
u32   lastUncompressedSize
4B    padding
i32   blobOffset
u32   blobSize
u8    compressionType    (0=None, 1=LZMA, 2=LZ4, 3=LZ4HC, 9=Oodle)
u8    uncompShift        (uncompressedSize = 1 << uncompShift)
8B    AlignStream
i32   blocksInfoCount
i32   nodesCount
i64   blocksInfoOff
i64   nodesInfoOff
i64   flagInfoOff
```

Then:
- `[blocksInfoOff..]`: `blocksInfoCount × u32` cumulative compressed sizes (LE)
- Per-block compressed size = `next_cumulative - prev_cumulative`
- `[nodesInfoOff..]`: node table
- `[block data]`: contiguous compressed blocks

## Block Decompression (BlbFile.cs:142-235)

| compressionType | Decryption | Decompressor |
|---|---|---|
| None (0) | BlbUtils.Decrypt | (none, write as-is) |
| Oodle (9) | **if compressedSize > 6**: BlbUtils.Decrypt first 16B; rest unchanged | OodleHelper.Decompress → OodleLZ_Decompress |
| LZMA (1) | (none) | SevenZipHelper.StreamDecompress |
| LZ4 (2) / LZ4HC (3) | BlbUtils.Decrypt (unconditional) | LZ4.Decompress |

**Note**: Oodle block first 6 bytes are OodleLZ stream header (magic `0x8C`). Blb3File prepends its own 6 bytes? No — re-check. The 6B difference between `compressedSize` (raw block size) and what Oodle expects may explain return-0 failures. Need to verify by reading first 6 bytes after decrypt.

## Oodle Magic Verification

- Decrypt output first 6 bytes of block 0 in 02050112.blk = `8c 06 01 85 83 89`
- `0x8C` is OodleLZ stream magic (confirmed via MhyFile.cs:116: `isOodle = compressedBlocksInfo[0] == 0x8C`)
- Data IS Oodle — decompression path correct

## 02050112.blk Real Values (block 0)

| Field | Value |
|---|---|
| blocksInfoSize | 175 |
| unk | 0x00000005 |
| headerKey | `9c07142ce496c73db51a5b258e911913` |
| compressionType | 9 (Oodle) |
| uncompShift | 18 → uncompressedSize = 262144 |
| blocksInfoCount | 1 |
| nodesCount | 2 |
| compressedSize (block 0) | 61708 |
| lastUncompressedSize | 124036 (last block's uncompressed size only; first block = 1<<18 = 262144) |

## Oodle DLL Inventory (2026-08-15)

| DLL | Size | Path | Exports |
|---|---|---|---|
| AnimeStudio.Ooz.dll | 202240 | `D:\Tools\AnimeStudio\AnimeStudio-net9-.../bin/` | `Ooz_Decompress` |
| oo2core_9_win64.dll | 606208 | `scripts/oo2core_9_win64.dll` | `OodleLZ_Decompress` only |

AnimeStudio vendored `zao/ooz` (202KB smaller than RAD official 606KB) — different ABI!

## Current Blocker

- OodleLZ_Decompress returns 0 (failure) on both:
  - AnimeStudio.Ooz.dll: `Ooz_Decompress` (14-arg StdCall WinDLL)
  - oo2core_9_win64.dll: `OodleLZ_Decompress` (14-arg Cdecl CDLL)
- Decrypt logic verified correct (GF256Exp/Log = 0 diffs)
- Compressed input first byte = 0x8C (correct Oodle magic) → data path valid
- Suspicion: calling convention mismatch (WinDLL vs CDLL) OR wrong argtypes/order

## Next Steps

1. Try `AnimeStudio.Ooz.dll` (WinDLL/StdCall) with correct argtypes from zao/ooz source:
   - `Ooz_Decompress(comp, compLen, raw, rawLen, ...)`
   - zao/ooz signature uses 14 args: comp, compLen, raw, rawLen, callback, callbackUser, decoderMemory, decoderMemorySize, threadPhase, verbosity, fuzzSafe, checkCRC, rawBuf, rawBufSize
2. If still 0: dump first 16B of decrypted block and verify they match expected OodleLZ sub-stream header format
3. After success: scale up to all 1441 bundles in 02050112.blk

## Tools / Scripts

- `scripts/blb_parser.py` — Blb3File parser (working for header/blocksInfo, Oodle block decompression blocked)
- `scripts/blb_crypto.py` — 4-step crypto (XOR/AES/RC4/GF256), 0 diff vs AnimeStudio
- `scripts/oodle.py` — DLL wrapper
- `scripts/diff_gf256.py` — table diff verifier (0 diffs)
- `scripts/parse_blb_header.py` — header reader
- `scripts/test_oodle_v2.py` — Oodle decompression tester (3 patterns)