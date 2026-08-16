"""diagnose_addon.py — check HeadShrink addon install status in Blender 5.2.0"""
import os
import sys
from pathlib import Path

ap = Path(os.environ["APPDATA"]) / "Blender Foundation" / "Blender" / "5.2" / "scripts" / "addons"
project_addon = Path(r"G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink\scripts\headshrink_addon.py")
dest = ap / "headshrink.py"

print(f"APPDATA addons dir: {ap}")
print(f"  exists: {ap.exists()}")
print(f"  dest addon: {dest}")
print(f"  exists: {dest.exists()}")
if dest.exists():
    print(f"  size: {dest.stat().st_size}")
    print(f"  same as source? {dest.read_bytes() == project_addon.read_bytes()}")
print()
print(f"Source addon: {project_addon}")
print(f"  exists: {project_addon.exists()}")
if project_addon.exists():
    print(f"  size: {project_addon.stat().st_size}")
