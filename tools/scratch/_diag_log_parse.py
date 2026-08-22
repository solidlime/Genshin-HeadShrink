"""Parse mizuki/log.txt to find the frame(s) with the largest draws per (vb0, ib) pair.

Output: a sorted list of (vb0, ib, frame, IndexCount, StartIndexLocation, BaseVertexLocation)
        filtered to entries with vb0=bbdaf598 (Mizuki main vertex buffer) and
        IndexCount > 100 (skip tiny draws like UI, effects).

# ponytail: one-shot log grep; no need for a regex library or full parser.
"""
import re
from collections import defaultdict
from pathlib import Path

LOG = Path(r"G:\XXMI-Launcher-Portable\Mods\mizuki\log.txt")
MAIN_VB0 = "bbdaf598"  # 889,040 bytes / 22,226 verts — confirmed Mizuki main mesh
MIN_INDEX_COUNT = 100

# State: track current frame number + current vb0/ib hash from the most recent
# draw's resource bindings (set just before DrawIndexed).
frame_re = re.compile(r"^(\d+) 3DMigoto\b")
# Resource bindings look like:
#   000001-vb0=<hash>-vs=<hash>-ps=<hash>
# but the log.txt uses "VertexBuffer<frame> = ..." and similar after frame header.
# Easier: scan DrawIndexed line and parse hash references near it.
# Pattern observed in Mizuki log (after sample):
#   DrawIndexed(IndexCount:24, StartIndexLocation:5532, BaseVertexLocation:4038)
# The vb0/ib hashes come from preceding "Hash = <hex>" lines.
draw_re = re.compile(
    r"DrawIndexed\(IndexCount:(\d+),\s*StartIndexLocation:(\d+),\s*BaseVertexLocation:(\d+)\)"
)
# Preceding hash bindings (last-seen wins)
vb0_hash_re = re.compile(r"\bvb0\s*=\s*([0-9a-f]{8})", re.IGNORECASE)
ib_hash_re  = re.compile(r"\bib\s*=\s*([0-9a-f]{8})", re.IGNORECASE)


def main():
    current_frame = None
    current_vb0 = None
    current_ib = None
    draws = []
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        m = frame_re.match(line)
        if m:
            current_frame = int(m.group(1))
            continue
        # Look for resource bindings (file naming hint in log?)
        mv = vb0_hash_re.search(line)
        if mv:
            current_vb0 = mv.group(1).lower()
        mi = ib_hash_re.search(line)
        if mi:
            current_ib = mi.group(1).lower()
        d = draw_re.search(line)
        if d:
            idx_count = int(d.group(1))
            start_idx = int(d.group(2))
            base_vtx = int(d.group(3))
            draws.append({
                "frame": current_frame,
                "vb0": current_vb0,
                "ib": current_ib,
                "index_count": idx_count,
                "start_index": start_idx,
                "base_vertex": base_vtx,
            })

    print(f"Total DrawIndexed entries: {len(draws)}")
    # Filter to Mizuki main vb0 + significant draws
    main = [d for d in draws if d["vb0"] == MAIN_VB0 and d["index_count"] >= MIN_INDEX_COUNT]
    print(f"With vb0={MAIN_VB0} and IndexCount >= {MIN_INDEX_COUNT}: {len(main)}")

    # Group by (vb0, ib) pair; pick frame with largest index_count per pair
    by_pair = defaultdict(list)
    for d in main:
        by_pair[(d["vb0"], d["ib"])].append(d)

    print("\n=== Per (vb0, ib) pair: pick max-IndexCount frame ===")
    summary = []
    for (vb0, ib), entries in by_pair.items():
        entries.sort(key=lambda e: e["index_count"], reverse=True)
        top = entries[0]
        summary.append((top["index_count"], top["frame"], top["vb0"], top["ib"], len(entries)))
    summary.sort(reverse=True)

    for idx_count, frame, vb0, ib, n in summary:
        print(f"  frame={frame:>6}  vb0={vb0}  ib={ib}  IndexCount={idx_count:>6}  ({n} draws)")

    # Also show: total distinct frames that have main vb0 draws
    distinct_frames = sorted({d["frame"] for d in main if d["frame"] is not None})
    print(f"\nFrames with vb0={MAIN_VB0} draws: {len(distinct_frames)}")
    print(f"  first 10: {distinct_frames[:10]}")
    print(f"  last 10:  {distinct_frames[-10:]}")

    # Find candidate head mesh: smallest reasonable mesh ~face/head size (4-8k tris)
    # Compare with body size (likely 10k+ tris)
    print("\n=== Heuristic head/body split by IndexCount ===")
    if summary:
        max_size = summary[0][0]
        # Head: ~30-70% of max
        head_candidates = [s for s in summary if 0.25 * max_size <= s[0] <= 0.85 * max_size]
        body_candidates = [s for s in summary if s[0] >= 0.85 * max_size]
        print(f"Max IndexCount: {max_size}")
        print(f"  Body candidates (>=85%): {len(body_candidates)}")
        for s in body_candidates[:5]:
            print(f"    frame={s[1]:>6}  vb0={s[2]}  ib={s[3]}  idx={s[0]:>6}")
        print(f"  Head candidates (25-85%): {len(head_candidates)}")
        for s in head_candidates[:5]:
            print(f"    frame={s[1]:>6}  vb0={s[2]}  ib={s[3]}  idx={s[0]:>6}")


if __name__ == "__main__":
    main()
