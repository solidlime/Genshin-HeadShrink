"""Try Dump mode (no class filter) to extract everything including Unknown ClassID 1152437153."""
import subprocess
from pathlib import Path

CLI = Path(r'D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\AnimeStudio.CLI.exe')

# Try Dump export type which dumps raw data for all assets
targets = [
    (r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\12189509.blk',
     r'D:\Documents\Default Project\Nilou\anime_nilou_12189509_dump'),
]

for blk_path, out_path in targets:
    Path(out_path).mkdir(parents=True, exist_ok=True)
    cmd = [
        str(CLI), blk_path, out_path,
        '--game', 'GI',
        '--export_type', 'Dump',
    ]
    print(f'CMD: {" ".join(cmd)}')
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print(f'Exit: {r.returncode}')
    if r.stdout:
        lines = r.stdout.splitlines()
        print(f'stdout: {len(lines)} lines')
        for ln in lines[:20]:
            print(f'  {ln[:300]}')
        if len(lines) > 20:
            print('  ...')
            for ln in lines[-5:]:
                print(f'  {ln[:300]}')
    if r.stderr:
        lines = r.stderr.splitlines()
        print(f'stderr: {len(lines)} lines')
        for ln in lines[:10]:
            print(f'  {ln[:300]}')

p = Path(targets[0][1])
files = list(p.rglob('*'))
print(f'\n{len(files)} files')
for f in sorted(files)[:50]:
    if f.is_file():
        print(f'  {f.relative_to(p)} ({f.stat().st_size} B)')