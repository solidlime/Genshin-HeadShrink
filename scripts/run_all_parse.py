"""run_all_parse.py — 7 char の parse_dump_dir.py を batch 実行。

# ponytail: 各 char は独立、並行性不要。失敗は許容 (後で個別リトライ)。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'parse_dump_dir.py'
CHARS = ['Ayaka', 'Chiori', 'Ganyu', 'Keqing C1', 'Kokomi', 'Mizuki', 'Nilou', 'Noelle']

DUMP_BASE = ROOT / 'assets' / 'Dump'
MESH_BASE = ROOT / 'assets' / 'Mesh'

failed = []
for char in CHARS:
    dump_dir = DUMP_BASE / char
    mesh_dir = MESH_BASE / char
    if not (dump_dir / 'log.txt').exists():
        print(f"[{char}] SKIP: no log.txt in {dump_dir}", file=sys.stderr)
        failed.append((char, 'no log.txt'))
        continue
    print(f"\n========== {char} ==========")
    res = subprocess.run(
        [sys.executable, str(SCRIPT), str(dump_dir),
         '--out-dir', str(mesh_dir), '--char', char],
        capture_output=True, text=True,
    )
    # Last 30 lines of output
    out_lines = res.stdout.strip().splitlines()[-30:]
    print('\n'.join(out_lines))
    if res.returncode != 0 or 'FAILED' in res.stdout:
        print(f"[{char}] non-zero exit or FAILED in output", file=sys.stderr)
        failed.append((char, 'parse_failed'))

print("\n========== Summary ==========")
if failed:
    for char, reason in failed:
        print(f"  FAIL: {char}  ({reason})")
    print(f"\n{len(failed)}/{len(CHARS)} chars failed")
    sys.exit(1)
else:
    print(f"All {len(CHARS)} chars processed OK")
