"""run_all_spec.py — auto_detect_vertex_range.py を全 8 キャラで実行。

# ponytail: 単純 batch、最小コード。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'auto_detect_vertex_range.py'
SPEC_BASE = ROOT / 'assets' / 'Spec'
DUMP_BASE = ROOT / 'assets' / 'Dump'
CHARS = ['Ayaka', 'Chiori', 'Ganyu', 'Keqing C1', 'Kokomi', 'Mizuki', 'Nilou', 'Noelle']

SPEC_BASE.mkdir(exist_ok=True)
for c in (SPEC_BASE / c for c in CHARS):
    c.mkdir(exist_ok=True)

for char in CHARS:
    dump_dir = DUMP_BASE / char
    spec_dir = SPEC_BASE / char
    log = dump_dir / 'log.txt'
    if not log.exists():
        print(f"[{char}] SKIP no log.txt", file=sys.stderr)
        continue
    out = spec_dir / 'groups.json'
    print(f"\n========== {char} → {out} ==========")
    res = subprocess.run(
        [sys.executable, str(SCRIPT), '--log', str(log), '--output', str(out)],
        capture_output=True, text=True,
    )
    print(res.stdout)
    if res.returncode != 0:
        print(f"[{char}] failed:", res.stderr[:500], file=sys.stderr)
