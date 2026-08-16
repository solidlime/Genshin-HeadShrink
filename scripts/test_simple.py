"""Test: open UnityPy on bundle 0 only. Verify basic load works."""
import os
import sys
import traceback

try:
    import UnityPy
except ImportError:
    print("UnityPy not installed")
    sys.exit(1)

NILOU_BIN = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
BUNDLE_SIZE = 262144

print(f"UnityPy: {UnityPy.__version__}", flush=True)

with open(NILOU_BIN, 'rb') as f:
    chunk = f.read(BUNDLE_SIZE)

print(f"Read {len(chunk)} bytes", flush=True)

try:
    env = UnityPy.load(chunk)
    print(f"Loaded: {env.__class__.__name__}", flush=True)
    objects = list(env.objects)
    print(f"Objects: {len(objects)}", flush=True)
    for obj in objects:
        print(f"  {obj.type.name} pathID={obj.path_id}", flush=True)
        try:
            tree = obj.read_typetree()
            print(f"    m_Name={tree.get('m_Name', '?')!r}", flush=True)
        except Exception as e:
            print(f"    read_typetree: {e}", flush=True)
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()

print("Done.", flush=True)
