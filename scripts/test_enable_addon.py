"""test_enable_addon.py — enable HeadShrink addon in Blender 5.2.0 background, report errors."""
import sys
import addon_utils

print("[1] Searching for headshrink...")
try:
    matches = [m for m in addon_utils.modules() if m.__name__.lower() == 'headshrink']
    print(f"    Found {len(matches)} module(s): {[m.__name__ for m in matches]}")
except Exception as e:
    print(f"    modules() FAILED: {type(e).__name__}: {e}")
    matches = []

if not matches:
    print("[FAIL] headshrink module not found by addon_utils!")
    sys.exit(1)

print("[2] Enabling...")
try:
    addon_utils.enable('headshrink', default_set=False, persistent=True)
    print("    enable() returned OK")
except Exception as e:
    print(f"    enable() FAILED: {type(e).__name__}: {e}")
    sys.exit(2)

print("[3] Verifying enable state...")
import bpy
print(f"    bpy.context.scene.headshrink_props = {bpy.context.scene.headshrink_props}")
print(f"    Has NHS_PT_panel: {hasattr(bpy.types, 'NHS_PT_panel')}")
if hasattr(bpy.types, 'NHS_PT_panel'):
    print(f"    bl_label: {bpy.types.NHS_PT_panel.bl_label}")
    print(f"    bl_category: {bpy.types.NHS_PT_panel.bl_category}")
    print(f"    bl_space_type: {bpy.types.NHS_PT_panel.bl_space_type}")
    print(f"    bl_region_type: {bpy.types.NHS_PT_panel.bl_region_type}")

print("[4] Saving userpref...")
try:
    bpy.ops.wm.save_userpref()
    print("    save_userpref OK")
except Exception as e:
    print(f"    save_userpref FAILED: {e}")

print("[5] Done.")
