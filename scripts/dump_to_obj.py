"""dump_to_obj.py — convert one 3DMigoto dump frame's vb0+ib to OBJ.
Usage:
    python dump_to_obj.py FRAME_NUMBER --dump-dir DIR --out OUT.obj
e.g. python dump_to_obj.py 167 --dump-dir G:\XXMI-Launcher-Portable\Mods\mizuki --out Mizuki_167.obj

# ponytail: minimal single-frame converter for Blender preview. Multi-frame
# or merged Position/IB is build_headshrink_mod.py territory.
"""
import argparse
import struct
import sys
from pathlib import Path

STRIDE = 40  # Genshin Impact standard: pos(12) + normal/tangent/uv/etc(28)


def find_files(dump_dir, frame):
    """Pick the first vb0 and ib .buf for the given frame number."""
    p = Path(dump_dir)
    vb0 = next(iter(p.glob(f"{frame:06d}-vb0=*.buf")), None)
    ib = next(iter(p.glob(f"{frame:06d}-ib=*.buf")), None)
    return vb0, ib


def vb0_to_obj(vb0_path, ib_path, out_path, stride=STRIDE, idx_bytes=4, max_indices=None):
    out_path = Path(out_path)
    vb0 = Path(vb0_path).read_bytes()
    ib = Path(ib_path).read_bytes()
    n_verts = len(vb0) // stride
    n_idx = len(ib) // idx_bytes
    use_idx = max_indices if max_indices else n_idx
    use_idx -= use_idx % 3  # triangle boundary
    print(f"vb0={len(vb0)}B / stride={stride} / {n_verts} verts")
    print(f"ib={len(ib)}B / idx_bytes={idx_bytes} / file={n_idx} indices, using {use_idx} ({use_idx // 3} triangles)")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Generated from {Path(vb0_path).name} + {Path(ib_path).name}\n")
        f.write(f"g {out_path.stem}\n")
        for v in range(n_verts):
            x, y, z = struct.unpack_from('<3f', vb0, v * stride)
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        # Skip degenerate triangles where indices reference nonexistent verts
        for i in range(0, use_idx, 3):
            if idx_bytes == 2:
                a, b, c = struct.unpack_from('<3H', ib, i * 2)
            else:
                a, b, c = struct.unpack_from('<3I', ib, i * 4)
            if max(a, b, c) >= n_verts:
                continue
            f.write(f"f {a + 1} {b + 1} {c + 1}\n")
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Single-frame dump vb0+ib -> OBJ.")
    ap.add_argument("frame", type=int, help="frame number (e.g. 167)")
    ap.add_argument("--dump-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=int, default=STRIDE)
    ap.add_argument("--idx-bytes", type=int, default=4, choices=[2, 4])
    ap.add_argument("--max-indices", type=int, default=None,
                    help="Limit to N indices (down-rounded to triangles). Use IndexCount from log.txt to avoid struct errors from padded ib files.")
    args = ap.parse_args()

    vb0, ib = find_files(args.dump_dir, args.frame)
    if not vb0 or not ib:
        print(f"missing: vb0={vb0} ib={ib}", file=sys.stderr)
        sys.exit(1)
    vb0_to_obj(vb0, ib, args.out, args.stride, args.idx_bytes)


if __name__ == "__main__":
    main()
