"""Convert mode without --types filter to export all 616 Mesh from 12189509."""
import subprocess
from pathlib import Path

CLI = Path(r'D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\AnimeStudio.CLI.exe')

blk = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\12189509.blk'
out = r'D:\Documents\Default Project\Nilou\anime_nilou_v4'

# Clear output
import shutil
if Path(out).exists():
    shutil.rmtree(out)
Path(out).mkdir(parents=True)

cmd = [str(CLI), blk, out, '--game', 'GI', '--export_type', 'Convert']
print(f'CMD: {" ".join(cmd)}')
r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
print(f'Exit: {r.returncode}')
if r.stdout:
    lines = r.stdout.splitlines()
    # Show summary
    export_lines = [l for l in lines if 'Exporting' in l]
    skip_lines = [l for l in lines if 'skipped' in l or 'exported' in l]
    print(f'Total log: {len(lines)}, Exporting: {len(export_lines)}')
    print('Last 10:')
    for ln in lines[-10:]:
        print(f'  {ln[:300]}')
if r.stderr:
    print(f'stderr: {r.stderr[:500]}')

# List actual outputs
p = Path(out)
files = [f for f in p.rglob('*') if f.is_file()]
print(f'\n{len(files)} files in {out}')
# Group by directory
from collections import defaultdict
by_dir = defaultdict(int)
for f in files:
    by_dir[str(f.relative_to(p).parent)] += 1
for d, n in sorted(by_dir.items()):
    print(f'  {d}: {n} files')

# Show Mesh subdirectory
mesh_dir = p / 'Mesh'
if mesh_dir.exists():
    print(f'\nMesh files ({len(list(mesh_dir.iterdir()))}):')
    for f in sorted(mesh_dir.iterdir())[:30]:
        print(f'  {f.name} ({f.stat().st_size} B)')