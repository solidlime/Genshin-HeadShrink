"""Inspect FrameAnalysis-2026-08-15-165509 to find Mizuki's relevant hashes."""
from pathlib import Path

fa = Path(r"G:\XXMI-Launcher-Portable\Mods\FrameAnalysis-2026-08-15-165509")

print("=== Top-level summary files (not .buf/.jpg) ===")
for f in sorted(fa.iterdir()):
    if f.is_file() and not (f.name.endswith(".buf") or f.name.endswith(".jpg")):
        size = f.stat().st_size
        print(f"  {f.name}  ({size:,} bytes)")
        if size < 4000 and size > 0:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")[:1500]
                print(f"    ---\n{content}\n    ---")
            except Exception as e:
                print(f"    READ_ERR: {e}")

print()
print("=== First few unique vb0 hashes in directory ===")
seen = {}
for f in fa.glob("*vb0=*.buf"):
    parts = f.name.split("-")
    for p in parts:
        if p.startswith("vb0="):
            vb0_hash = p[4:].split(".")[0]
            if vb0_hash not in seen:
                seen[vb0_hash] = (f.stat().st_size, f.name)
            break
# Sort by size desc
sorted_hashes = sorted(seen.items(), key=lambda kv: -kv[1][0])
for h, (size, sample) in sorted_hashes[:15]:
    print(f"  vb0={h}  size={size:,}  sample: {sample}")
