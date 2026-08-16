"""Step 7: Try UnityPy load on v2 data
- 02050112 decompressed data contains 1441 Unity serialized files
- Try UnityPy.load() to find Mesh objects
- If fails, try alternative parsing
"""
import sys
from pathlib import Path
sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')

PATH = r'D:\Documents\Default Project\Nilou\nilou_full_v2.bin'
OUT = Path(PATH)
print(f'File: {PATH}')
print(f'Size: {OUT.stat().st_size:,} bytes')

# Try UnityPy
try:
    import UnityPy
    print('\nTrying UnityPy.load()...')
    env = UnityPy.load(str(PATH))
    print(f'UnityPy loaded: {len(env.objects)} objects')

    from collections import Counter
    type_counts = Counter()
    mesh_objects = []
    for obj in env.objects:
        try:
            tname = obj.type.name
            type_counts[tname] += 1
            if tname == 'Mesh':
                mesh_objects.append(obj)
        except:
            type_counts['?unknown'] += 1

    print(f'\nType distribution:')
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1])[:30]:
        print(f'  {t}: {c}')

    if mesh_objects:
        print(f'\nFOUND {len(mesh_objects)} Mesh objects!')
        for m in mesh_objects[:5]:
            try:
                print(f'  path_id={m.path_id} name={m.m_Name}')
            except:
                pass
except Exception as e:
    print(f'UnityPy failed: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
