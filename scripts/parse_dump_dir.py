"""parse_dump_dir.py — auto-pick best frame per (vb0, ib) pair and emit OBJs.

Usage:
    python parse_dump_dir.py <frame_analysis_dir> --out-dir <mesh_dir> [--char NAME]

Reads <dir>/log.txt for DrawIndexed(...) entries and their preceding resource
bindings (vb0=/ib= hash from Map/Unmap/Dumping Buffer lines), groups draws by
(vb0, ib) hash pair, picks the frame with the largest IndexCount per pair, and
calls dump_to_obj.py for each (one OBJ per mesh part).

Output: <out_dir>/<char>_<vb0>_<ib>_f<frame>.obj  + a summary groups.json.

# ponytail: replaces hand-picking frames per character; the only per-character
# knob is which vb0/ib hash pair corresponds to the head (vs body, dress, ...).
"""
import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def parse_log(log_path):
    """Walk log.txt once, return list of draws: {frame, vb0, ib, ic, start, base}."""
    frame_re = re.compile(r"^(\d+) 3DMigoto")
    # Match Map/Unmap/Dumping Buffer: hash=<hex> appears inline near resource binding lines.
    # For draw association, we look at the 10 lines preceding the DrawIndexed.
    draw_re = re.compile(
        r"^(\d+) DrawIndexed\(IndexCount:(\d+),\s*StartIndexLocation:(\d+),\s*BaseVertexLocation:(\d+)\)"
    )
    vb_dump_re = re.compile(r"Dumping Buffer .*-vb0=([0-9a-f]+)\.buf")
    ib_dump_re = re.compile(r"Dumping Buffer .*-ib=([0-9a-f]+)\.buf")
    # Also catch resource bindings set via Map(... hash=<hex>)
    map_re = re.compile(r"^(\d+) Map\(.*hash=([0-9a-f]{8,16})")
    unmap_re = re.compile(r"^(\d+) Unmap\(.*hash=([0-9a-f]{8,16})")

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()

    # Build frame -> {vb0, ib} hash bindings from Dumping Buffer lines (most reliable).
    frame_vb0 = defaultdict(set)
    frame_ib = defaultdict(set)
    for line in lines:
        m = re.match(r"^(\d+) 3DMigoto Dumping Buffer .*-vb0=([0-9a-f]+)", line)
        if m:
            frame_vb0[int(m.group(1))].add(m.group(2))
            continue
        m = re.match(r"^(\d+) 3DMigoto Dumping Buffer .*-ib=([0-9a-f]+)", line)
        if m:
            frame_ib[int(m.group(1))].add(m.group(2))

    # For each draw, determine vb0/ib via the per-frame dumped bindings
    # (frame_vb0 / frame_ib dicts). If multiple vb0 in same frame (rare), pick first.
    draws = []
    for i, line in enumerate(lines):
        d = draw_re.match(line)
        if not d:
            continue
        frame = int(d.group(1))
        ic = int(d.group(2))
        start = int(d.group(3))
        base = int(d.group(4))
        vb0_list = sorted(frame_vb0.get(frame, set()))
        ib_list = sorted(frame_ib.get(frame, set()))
        draws.append({
            "frame": frame,
            "vb0": vb0_list[0] if vb0_list else None,
            "ib": ib_list[0] if ib_list else None,
            "vb0_count": len(vb0_list),
            "ib_count": len(ib_list),
            "index_count": ic, "start_index": start, "base_vertex": base,
        })
    return draws, frame_vb0, frame_ib


def group_draws(draws, min_ic=100):
    """Group draws by (vb0, ib); return {pair: [draws...]} for draws with ic >= min_ic."""
    by_pair = defaultdict(list)
    for d in draws:
        if d["index_count"] < min_ic:
            continue
        if not d["vb0"] or not d["ib"]:
            continue
        by_pair[(d["vb0"], d["ib"])].append(d)
    return by_pair


def pick_best_per_pair(by_pair):
    """For each (vb0, ib) pair, return the draw with max IndexCount."""
    out = []
    for (vb0, ib), entries in by_pair.items():
        best = max(entries, key=lambda e: e["index_count"])
        out.append({
            "vb0": vb0, "ib": ib,
            "frame": best["frame"],
            "index_count": best["index_count"],
            "start_index": best["start_index"],
            "base_vertex": best["base_vertex"],
            "draws_in_pair": len(entries),
        })
    out.sort(key=lambda r: r["index_count"], reverse=True)
    return out


def has_files_for_frame(dump_dir, frame, vb0, ib):
    """Confirm both vb0+ib .buf exist for the given frame."""
    p = Path(dump_dir)
    return (p / f"{frame:06d}-vb0={vb0}-vs=").exists() or any(
        p.glob(f"{frame:06d}-vb0={vb0}-*.buf")
    ), any(p.glob(f"{frame:06d}-ib={ib}-*.buf"))


def main():
    ap = argparse.ArgumentParser(description="Parse FrameAnalysis dir → per-pair OBJ outputs.")
    ap.add_argument("dump_dir", help="FrameAnalysis directory (must contain log.txt)")
    ap.add_argument("--out-dir", required=True, help="Where to write OBJs + summary")
    ap.add_argument("--char", default="Mesh", help="Char name prefix for OBJ files")
    ap.add_argument("--min-ic", type=int, default=100, help="Skip draws with IndexCount < N")
    ap.add_argument("--dump-to-obj", default=None,
                    help="Path to dump_to_obj.py (default: same dir as this script)")
    ap.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    args = ap.parse_args()

    dump_dir = Path(args.dump_dir)
    log = dump_dir / "log.txt"
    if not log.exists():
        sys.exit(f"log.txt not found in {dump_dir}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dump_to_obj = args.dump_to_obj or (Path(__file__).parent / "dump_to_obj.py")
    if not Path(dump_to_obj).exists():
        sys.exit(f"dump_to_obj.py not found at {dump_to_obj}")

    draws, frame_vb0, frame_ib = parse_log(log)
    print(f"Total DrawIndexed: {len(draws)}")
    by_pair = group_draws(draws, args.min_ic)
    print(f"Distinct (vb0, ib) pairs with ic >= {args.min_ic}: {len(by_pair)}")

    summary = pick_best_per_pair(by_pair)
    print(f"\n=== Best frame per (vb0, ib) pair ===")
    for s in summary:
        has_vb0, has_ib = has_files_for_frame(dump_dir, s["frame"], s["vb0"], s["ib"])
        flag = "" if (has_vb0 and has_ib) else "  ⚠ MISSING FILES"
        print(f"  frame={s['frame']:>6}  vb0={s['vb0']}  ib={s['ib']}  ic={s['index_count']:>6}{flag}")

    # Write summary
    summary_path = out_dir / f"{args.char}_dump_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary: {summary_path}")

    if args.dry_run:
        print("(dry run, no OBJ written)")
        return

    # Run dump_to_obj.py for each pair
    for s in summary:
        has_vb0, has_ib = has_files_for_frame(dump_dir, s["frame"], s["vb0"], s["ib"])
        if not (has_vb0 and has_ib):
            print(f"  skip frame={s['frame']} vb0={s['vb0']} (files missing)")
            continue
        out_obj = out_dir / f"{args.char}_{s['vb0'][:8]}_{s['ib'][:8]}_f{s['frame']}.obj"
        cmd = [
            sys.executable, str(dump_to_obj),
            str(s["frame"]),
            "--dump-dir", str(dump_dir),
            "--out", str(out_obj),
            "--max-indices", str(s["index_count"]),
        ]
        print(f"  -> {out_obj.name}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"     FAILED: {res.stderr[:300]}")


if __name__ == "__main__":
    main()
