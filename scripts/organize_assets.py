"""organize_assets.py — 一回限り、assets/ 構造作って散らばってるファイルを整理。

# ponytail: 単純な file move + 構造作成。エラーは raise で停止、安全側。
"""
import shutil
from pathlib import Path

ROOT = Path(r"G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink")
NILOU_MESH = Path(r"D:\Documents\Default Project\Nilou\anime_nilou_08476697\Mesh")
MITYA_MESH = Path(r"D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh")
TIGHNARI_MESH = Path(r"D:\Documents\Default Project\Nilou\anime_nilou_v4\Mesh")

ASSETS = ROOT / "assets"
MESH = ASSETS / "Mesh"
SPEC = ASSETS / "Spec"
DUMP = ASSETS / "Dump"
PREVIEW = ASSETS / "Preview"


def makedir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    print(f"  mkdir: {p}")


def safe_copytree(src: Path, dst: Path, glob_pat: str = "*"):
    """Copy files matching glob from src into dst (create if needed)."""
    if not src.exists():
        print(f"  skip: {src} missing")
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in src.glob(glob_pat):
        if f.is_file():
            shutil.copy2(f, dst / f.name)
            n += 1
    print(f"  copy: {src} ({glob_pat}) -> {dst} ({n} files)")
    return n


def main():
    print("=== creating directory structure ===")
    makedir(ASSETS)
    makedir(MESH)
    makedir(SPEC)
    makedir(DUMP)
    makedir(PREVIEW)

    # Per-character subdirectories.
    for sub in ["Nilou", "Mitya", "Tighnari", "Mizuki"]:
        makedir(MESH / sub)

    print("\n=== copying Mesh OBJs ===")
    # Nilou mesh dir contains Mizuki OBJs (placed there for Blender import).
    # Need to separate: take only Mizuki_*.obj for Mizuki, others for Nilou.
    nilou_dst = MESH / "Nilou"
    mizuki_dst = MESH / "Mizuki"
    if NILOU_MESH.exists():
        for f in NILOU_MESH.iterdir():
            if not f.is_file() or not f.name.lower().endswith('.obj'):
                continue
            if f.name.startswith('Mizuki_'):
                shutil.copy2(f, mizuki_dst / f.name)
            else:
                shutil.copy2(f, nilou_dst / f.name)
        n_n = len(list(nilou_dst.glob('*.obj')))
        n_m = len(list(mizuki_dst.glob('*.obj')))
        print(f"  sorted {NILOU_MESH} -> Nilou={n_n}, Mizuki={n_m}")

    safe_copytree(MITYA_MESH, MESH / "Mitya", "*.obj")
    safe_copytree(TIGHNARI_MESH, MESH / "Tighnari", "*.obj")

    print("\n=== copying Spec JSONs ===")
    spec_dst = SPEC
    spec_dst.mkdir(exist_ok=True)
    # Existing spec sources
    for src_dir in [ROOT / "scripts" / "prefabs", ROOT / "scripts"]:
        if not src_dir.exists():
            continue
        for f in src_dir.glob("*.json"):
            # Skip headshrink_addon sub-files
            if f.name in ("mizuki_groups.json", "spec_mizuki.json"):
                continue
            shutil.copy2(f, spec_dst / f.name)
            print(f"  copy: {f} -> {spec_dst / f.name}")

    print("\n=== summary ===")
    for sub in MESH.iterdir():
        if sub.is_dir():
            n = len(list(sub.glob('*.obj')))
            print(f"  assets/Mesh/{sub.name}: {n} OBJs")
    n_spec = len(list(SPEC.glob('*.json')))
    print(f"  assets/Spec: {n_spec} JSONs")


if __name__ == "__main__":
    main()
