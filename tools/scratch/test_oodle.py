"""02050112.blk Oodle + decrypt diagnosis. Tests both with and without BlbUtils.Decrypt."""
import sys, struct, io
from pathlib import Path
from collections import Counter

sys.path.insert(0, r"G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts")
from blb_parser import Blb3File, scan_bundles
from blb_crypto import decrypt as blb_decrypt
from oodle import oodle_decompress

BLK = r"G:\Epic Games\GenshinImpact\games\Genshin Impact game\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk"

with open(BLK, "rb") as f:
    data = f.read()

bundles = scan_bundles(data)
off, b = bundles[0]
print(f"Bundle at {off:#x}, blocks={len(b.blocks)}")
print(f"Block 0: compressed={b.blocks[0].compressed_size} uncompressed={b.blocks[0].uncompressed_size} flags={b.blocks[0].flags}")

# Get raw block bytes
compressed_raw = bytearray(b.block_data[:b.blocks[0].compressed_size])
compressed_dec = bytearray(compressed_raw)
if b.blocks[0].compressed_size > 6:
    blb_decrypt(b._hk, compressed_dec)

# First 32 bytes comparison
print(f"First 32 bytes (raw)    : {compressed_raw[:32].hex()}")
print(f"First 32 bytes (decrypt): {compressed_dec[:32].hex()}")
print(f"Identical: {compressed_raw == compressed_dec}")

# Test 1: with decrypt
print("\n[Test A] With BlbUtils.Decrypt + Oodle:")
try:
    n = oodle_decompress(bytes(compressed_dec), b.blocks[0].uncompressed_size)
    print(f"  OK: {n} bytes decompressed")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 2: without decrypt
print("\n[Test B] Raw bytes (no decrypt) + Oodle:")
try:
    n = oodle_decompress(bytes(compressed_raw), b.blocks[0].uncompressed_size)
    print(f"  OK: {n} bytes decompressed")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 3: Oodle signature/magic on raw bytes
print(f"\n[Test C] Magic byte check on raw: {compressed_raw[0]:#04x} {compressed_raw[1]:#04x} {compressed_raw[2]:#04x} {compressed_raw[3]:#04x}")
print(f"[Test C] Magic byte check on dec : {compressed_dec[0]:#04x} {compressed_dec[1]:#04x} {compressed_dec[2]:#04x} {compressed_dec[3]:#04x}")