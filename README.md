# HeadShrink — Genshin Impact Head-Shrink Mod Tool

Shrink any character's head in Blender with a live preview, then export a ready-to-use XXMI-Launcher mod. No modding knowledge required — if you can take a frame dump, you can make a mod.

## Requirements

- Windows
- [Blender 5.2.0 LTS](https://www.blender.org/download/lts/)
- [XXMI-Launcher](https://github.com/SpectrumQT/XXMI-Launcher) with 3DMigoto enabled

## Installation (once)

1. Right-click `launch_blender.bat` → **Run as administrator**
   - This links the addon into Blender automatically. If it fails, enable Windows Settings → For developers → Developer Mode and try again.
2. From then on, just double-click `launch_blender.bat` to start Blender with HeadShrink ready.

> Manual install also works: Blender → Edit → Preferences → Add-ons → Install → `scripts/headshrink_addon.py`

## Step 0 — Capture a Frame Dump (per character)

HeadShrink builds mods from 3DMigoto frame dumps. You need **two captures**: one with the character's mouth hidden, one with it visible.

1. In game, open the character's profile screen facing the camera
2. Turn on 3DMigoto Hunting mode (numpad `0`)
3. Cycle through vertex buffers with `*` / `-` until the **mouth disappears**, then press `F8` once to capture
4. Switch to another character and back until the **mouth reappears**, then press `F8` again
5. Repeat steps 3–4 a couple of times so you have both states covered
6. Move the resulting `FrameAnalysis-*` folder(s) somewhere like `assets/Dump/<CharacterName>/`

## Build the Mod (5 steps)

Open the `HeadShrink` tab in Blender's N-panel and work top to bottom.

### 1. Dump Directory
Point it at your dump folder (e.g. `assets/Dump/Yanfei`). The character name is filled in automatically.

### 2. Register Meshes
Click **Analyze Dump** — it lists the mesh pairs found in the dump. Click each entry to preview it, then use **表示中のペアを登録** (Register Displayed Pair) to assign it as `BODY`, `MOUTH`, `EYES`, or `BROW`. One `BODY` is required; face parts are optional. Re-opening the same dump folder no longer clears your registrations.

### 3. Auto Setup
One click builds the whole preview scene: loads the meshes, places them, and creates the shrink box.

### 4. Adjust the Head
Move the shrink box over the head and tune the sliders — the preview updates live. Handy buttons:

- **Reposition Faces** — snap face parts back onto the head
- **Auto Fill Offsets** — measure gaps after shrinking and fill the offset fields for you
- **Save Char Config** — save this character's settings (asks before overwriting)

### 5. Export
Set an output folder and click **Mod Export**. You get a `.ini` plus buffers — a complete mod. The summary window opens the output folder for you.

## Try It In Game

Copy the exported folder into XXMI's `Mods` directory (e.g. `…\XXMI-Launcher\Mods\Mods\HeadShrink\Yanfei\`), launch the game through XXMI, and check the result. The body follows animations seamlessly; only the head is shrunk.

> **Updating from an older version?** Re-export **all** of your character mods, not just the one you're working on. Face meshes are shared between characters internally, so one outdated mod can break the others (flickering, squashed mouths). Mixed old/new exports are not supported.

## FAQ

**Q. My mod's mouth effect shows up on other characters too**
A. Face meshes are shared between characters internally. Recent exports guard against this automatically — re-export with the latest version of the addon.

**Q. The head/eyes/mouth flicker between shrunk and normal size, or the mouth collapses**
A. Fixed in recent versions (idempotent shaders + expression-variant tolerance). Re-export **all** your character mods with the latest addon — a single leftover mod made with an older version can still trigger it.

**Q. Weird textures flash all over the screen**
A. Usually caused by a mod made with an older version. Re-export with the latest version.

**Q. The face offset fields (eyes/mouth/brow) don't do anything**
A. They were temporarily disabled and are working again in the latest version. Re-export to pick up the fix. Note: when several shrunken characters are on screen at once (e.g. the party screen), shared face parts follow whichever character comes first alphabetically — solo play is unaffected.

**Q. `launch_blender.bat` won't start Blender**
A. Run it as administrator once, or turn on Developer Mode (Windows Settings → For developers).

## Credits

- Built on [3DMigoto](https://github.com/bo3b/3Dmigoto) / [XXMI-Launcher](https://github.com/SpectrumQT/XXMI-Launcher)
- Face-gating approach inspired by effieface's `FaceDiffuse $is` technique
- Oodle decompression uses RAD Game Tools' `oo2core_9_win64.dll`
