"""Extract Nilou meshes from 12189509.blk and 10353076.blk via AnimeStudio."""
import subprocess, os
from pathlib import Path

ANIME = r'D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\AnimeStudio.CLI.exe'
OUT_BASE = Path(r'D:\Documents\Default Project\Nilou')
CANDIDATES = [
    (r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\12189509.blk', 'nilou_12189509'),
    (r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\10353076.blk', 'nilou_10353076'),
]

for src, label in CANDIDATES:
    if not os.path.exists(src):
        print(f'SKIP missing: {src}')
        continue
    out_dir = OUT_BASE / f'anime_{label}'
    out_dir.mkdir(exist_ok=True)
    print(f'\n=== {label} ===')
    cmd = [
        ANIME, src, str(out_dir),
        '--game', 'GI',
        '--names', 'avatar_girl_sword_nilou',
        '--types', 'Mesh,SkinnedMeshRenderer,Texture2D,Material',
        '--export_type', 'Convert',
        '--silent',
    ]
    print(' '.join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        print(f'exit={result.returncode}')
        # Tail of stdout/stderr
        log = result.stdout[-2000:] if result.stdout else ''
        if result.stderr:
            log += '\n--- stderr ---\n' + result.stderr[-1000:]
        print(log)
    except subprocess.TimeoutExpired:
        print('TIMEOUT after 600s')
    # List output
    if out_dir.exists():
        files = list(out_dir.rglob('*'))
        files = [f for f in files if f.is_file()]
        print(f'Output files: {len(files)}')
        for f in files[:50]:
            print(f'  {f.relative_to(out_dir)}')