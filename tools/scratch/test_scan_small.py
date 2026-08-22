"""Quick scan of first 50 bundles with full traceback capture."""
import os
import sys
import time
import traceback

try:
    import UnityPy
except ImportError:
    print("UnityPy not installed")
    sys.exit(1)

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144

print("Loading 237MB file...", flush=True)
with open(NILOU_BIN, 'rb') as f:
    data = f.read()
print(f"Loaded {len(data):,} bytes", flush=True)

print("\nScanning first 50 bundles...", flush=True)
nonempty = []
for bundle_idx in range(50):
    offset = bundle_idx * BUNDLE_SIZE
    chunk = data[offset:offset + BUNDLE_SIZE]
    try:
        env = UnityPy.load(chunk)
        objects = list(env.objects)
        if objects:
            types = [obj.type.name for obj in objects]
            nonempty.append((bundle_idx, types))
            print(f"  bundle {bundle_idx:4d}  types={types}", flush=True)
    except Exception as e:
        print(f"  bundle {bundle_idx:4d}  EXCEPTION: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        # Don't crash, continue

print(f"\nNon-empty in first 50: {len(nonempty)}", flush=True)
print(f"Any output before crash took this session."

# Also try sampling 200-250
print("\nSampling 200-250...", flush=True)
nonempty2 = []
for bundle_idx in range(200, 250):
    offset = bundle_idx * BUNDLE_SIZE
    chunk = data[offset:offset + BUNDLE_SIZE]
    try:
        env = UnityPy.load(chunk)
        objects = list(env.objects)
        if objects:
            types = [obj.type.name for obj in objects]
            nonempty2.append((bundle_idx, types))
    except Exception as e:
        print(f"  bundle {bundle_idx:4d}  EXCEPTION: {type(e).__name__}: {e}", flush=True)

print(f"\nNon-empty in 200-250: {len(nonempty2)}", flush=True)
print(f"Done.", flush=True)
