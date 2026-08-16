"""Extract 10353076.blk with AnimeStudio (no type filter)."""
import subprocess, os
CLI = r"D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\AnimeStudio.CLI.exe"
SRC = r"G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\10353076.blk"
OUT = r"D:\Documents\Default Project\Nilou\anime_nilou_10353076"
os.makedirs(OUT, exist_ok=True)
r = subprocess.run([CLI, SRC, OUT, "--game", "GI", "--export_type", "Convert"],
                   capture_output=True, text=True)
print("returncode:", r.returncode)
print("--- stdout (last 60) ---")
lines = r.stdout.splitlines()
for line in lines[-60:]:
    print(line)
print("--- stderr (last 20) ---")
err_lines = r.stderr.splitlines()
for line in err_lines[-20:]:
    print(line)
print("\n--- output dirs ---")
for root, dirs, files in os.walk(OUT):
    for f in files[:30]:
        full = os.path.join(root, f)
        sz = os.path.getsize(full)
        print(f"  {os.path.relpath(full, OUT):60s} {sz:>12,}B")
    if len(files) > 30:
        print(f"  ... and {len(files)-30} more in {root}")
