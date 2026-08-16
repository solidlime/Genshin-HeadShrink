# HeadShrink Mod — 原神モデル拡縮 mod ツール

原神 (Genshin Impact) のキャラ 3D モデルを抽出し、Blender で部位別拡縮 → XXMI-Launcher (3DMigoto) 形式の mod として書き出すツール群。

## ディレクトリ構造
```
HeadShrink/
├── scripts/                   — 全 Python スクリプト (Blender addon, parser, builders)
├── assets/
│   ├── Mesh/<Char>/           — キャラ別 OBJ ファイル (Blender addon 入力)
│   ├── Spec/<Char>.json       — キャラ別 spec 設定
│   ├── Dump/<Char>/           — ゲーム内 dump (3DMigoto FrameAnalysis)
│   └── Preview/               — render preview, mod 出力先
├── notes/                     — 開発メモ
├── .spec/                     — SDD 仕様 (PLAN/SPEC/TODO/KNOWLEDGE)
├── AGENTS.md                  — プロジェクトガイド (Nous memory ops, SDD, subagent)
├── README.md                  — このファイル
├── assets.xml                 — 抽出済みアセット一覧
├── 引き継ぎ書.md               — 手動引継ぎドキュメント (補助)
└── .gitignore
```

## 技術構成
- **言語**: Python 3.12 (scripts/), Blender 5.2.0 Python (addon)
- **主要依存**: lz4, UnityPy 1.25.3, ctypes (oo2core_9_win64.dll)
- **外部ツール**: AnimeStudio CLI, Blender 5.2.0, XXMI-Launcher, 3DMigoto dump
- **ゲーム**: 原神 (`G:\HoYoPlay\games\Genshin Impact\`)

## クイックスタート

### 1. キャラ mesh を OBJ 化 (Blender プレビュー)
```bash
# dump_to_obj.py で FrameAnalysis を OBJ に変換
python scripts/dump_to_obj.py ^
    --vb "assets\Dump\Nilou\000001-vb0=<hash>.buf" ^
    --ib "assets\Dump\Nilou\000001-ib=<hash>.buf" ^
    --out assets\Mesh\Nilou\Nilou_body.obj

# または parse_dump_dir.py で一括変換
python scripts/parse_dump_dir.py ^
    --dump-dir assets\Dump\Nilou ^
    --out-dir assets\Mesh\Nilou
```

### 2. Blender で拡縮
```bash
# addon install + Blender 起動
launch_blender.bat  (もしくは手動: Edit → Preferences → Add-ons → Install scripts/headshrink_addon.py)

# N-panel → HeadShrink:
#   Mesh Dir: G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink\assets\Mesh\<Char>
#   Prefab: Auto
#   [Import Meshes] → slider 調整 → [Apply Transforms] → [Export Scaled OBJs]
```

### 3. 3DMigoto mod 化
```bash
# spec 自動生成 (log.txt から vertex range 推定)
python scripts/auto_detect_vertex_range.py ^
    --log assets\Dump\<Char>\log.txt ^
    --out assets\Spec\<Char>_groups.json

# mod フォルダ生成
python scripts\build_headshrink_mod.py ^
    --char <Char> ^
    --dump-dir assets\Dump\<Char> ^
    --output-dir assets\Preview\<Char> ^
    --spec assets\Spec\<Char>_groups.json ^
    --scale HEAD=0.65
```

### 4. XXMI-Launcher に配置
生成された `assets\Preview\<Char>\<Char>.ini` と `<Char>*.{buf,ib}` を
`G:\XXMI-Launcher-Portable\Mods\Mods\<Char>\` にコピー → 原神起動で確認。

## 対応キャラ
- ✅ **Nilou** (Avatar_Girl_Sword_Nilou, 08476697.blk) — 19 OBJs
- ✅ **Mitya NPC** (00514567.blk) — 25 OBJs
- ✅ **Tighnari** (12189509.blk) — 524 OBJs (scene 含む)
- ✅ **Mizuki** (FrameAnalysis dump) — 12 OBJs (8 parts auto-generated)
- ⚠️ MdbComponent 形式キャラ（複数）は追加解析必要

## 詳細
- 仕様: `.spec/SPEC.md`
- TODO: `.spec/TODO.md`
- 知識・調査: `.spec/KNOWLEDGE.md`
- 旧引継ぎ: `引き継ぎ書.md`
