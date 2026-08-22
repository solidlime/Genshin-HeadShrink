"""Run AnimeStudio extraction with simpler subprocess approach - no --names filter."""
import subprocess
from pathlib import Path

CLI = Path(r'D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\AnimeStudio.CLI.exe')

TARGETS = [
    (r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\12189509.blk',
     r'D:\Documents\Default Project\Nilou\anime_nilou_12189509'),
    (r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\10353076.blk',
     r'D:\Documents\Default Project\Nilou\anime_nilou_10353076'),
]

for blk_path, out_path in TARGETS:
    Path(out_path).mkdir(parents=True, exist_ok=True)
    cmd = [
        str(CLI),
        blk_path,
        out_path,
        '--game', 'GI',
        '--types', 'Mesh,SkinnedMeshRenderer,Texture2D,Material',
        '--export_type', 'Convert',
    ]
    print(f'CMD: {" ".join(cmd)}')
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print(f'Exit: {r.returncode}')
        if r.stdout:
            # Show first/last lines only to save context
            lines = r.stdout.splitlines()
            print(f'stdout: {len(lines)} lines')
            for ln in lines[:3]:
                print(f'  {ln[:200]}')
            if len(lines) > 3:
                print(f'  ...')
                for ln in lines[-3:]:
                    print(f'  {ln[:200]}')
        if r.stderr:
            lines = r.stderr.splitlines()
            print(f'stderr: {len(lines)} lines')
            for ln in lines[:5]:
                print(f'  {ln[:200]}')
    except subprocess.TimeoutExpired:
        print('TIMEOUT')
    except Exception as e:
        print(f'ERROR: {e}')
    print()

# List outputs
for _, out_path in TARGETS:
    p = Path(out_path)
    if p.exists():
        files = list(p.rglob('*'))
        print(f'\n{out_path}: {len(files)} files')
        # Show top-level dirs
        dirs = sorted(set(f.parent for f in files if f.is_file()))
        for d in dirs[:20]:
            n = len(list(d.iterdir()))
            print(f'  {d.relative_to(p)}: {n} files')