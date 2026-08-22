"""Run AnimeStudio CLI on 08476697.blk to extract Nilou mesh."""
import subprocess
import os

CLI = r'D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\AnimeStudio.CLI.exe'
INPUT = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\08476697.blk'
OUTPUT = r'D:\Documents\Default Project\Nilou\anime_nilou_08476697'

os.makedirs(OUTPUT, exist_ok=True)

cmd = [CLI, INPUT, OUTPUT, '--game', 'GI', '--export_type', 'Convert']
print(f"Running: {' '.join(cmd)}")
result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
print(f"Exit code: {result.returncode}")
print(f"=== stdout (last 50 lines) ===")
for line in result.stdout.split('\n')[-50:]:
    print(line)
print(f"=== stderr (last 20 lines) ===")
for line in result.stderr.split('\n')[-20:]:
    print(line)
print(f"\n=== Output dir ===")
for root, dirs, files in os.walk(OUTPUT):
    rel = os.path.relpath(root, OUTPUT)
    sub_files = sorted(files)
    print(f"  {rel}/")
    for f in sub_files[:20]:
        size = os.path.getsize(os.path.join(root, f))
        print(f"    {f}  ({size:,} bytes)")
    if len(sub_files) > 20:
        print(f"    ... {len(sub_files)-20} more")
