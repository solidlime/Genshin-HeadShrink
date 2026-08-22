"""Quick frame 15 + 911ff708/9ccbfb88 file existence check."""
from pathlib import Path

MI = Path(r"G:\XXMI-Launcher-Portable\Mods\mizuki")

print("=== frame 15 files ===")
for p in sorted(MI.glob("000015-*.buf")):
    print(f"  {p.name}  size={p.stat().st_size}")
print()

print("=== hash anywhere ===")
print(f"  vb0=911ff708: {len(list(MI.glob('*911ff708*.buf')))} files")
print(f"  ib=9ccbfb88:  {len(list(MI.glob('*9ccbfb88*.buf')))} files")
print()

# Also check the closest hashes (prefix collision)
print("=== 9 prefix hashes (like 9ccbfb88) ===")
for p in sorted(MI.glob("*9c*.buf"))[:10]:
    print(f"  {p.name}")
print()

# Check log.txt for those hashes
print("=== log.txt references ===")
log = MI / "log.txt"
if log.exists():
    text = log.read_text(encoding="utf-8", errors="replace")
    for h in ["911ff708", "9ccbfb88"]:
        refs = [ln.strip() for ln in text.splitlines() if h in ln][:5]
        print(f"  '{h}' lines ({len(refs)}):")
        for ln in refs:
            print(f"    {ln[:200]}")
