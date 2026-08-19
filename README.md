# HeadShrink — 原神 頭部縮小 Mod 作成ツール

Blender 上でキャラの頭部をプレビューしながら縮小し、XXMI-Launcher (3DMigoto) 用の差分 Mod（`Body` は VB置換 / 顔は CopyDispatch）をそのまま書き出すツール。Noelle は実ゲームでズレなし確認済み。

## 必要環境

- Windows / Blender 5.2.0 LTS / Python 3.12
- XXMI-Launcher + 3DMigoto（FrameAnalysis ダンプ取得用）
- 管理者権限（初回のみ、アドオンを symlink で配置するため。開発者モードでも可）

## インストール（1回だけ）

1. `launch_blender.bat` を **右クリック → 管理者として実行**
   - `scripts/headshrink_addon.py` が `…\Blender\5.2\scripts\addons\headshrink.py` に symlink される（失敗時はエラーで停止、コピーに勝手にフォールバックしない）
   - 初回はアドオンが自動で有効化され `userpref.blend` に保存される
2. 以降は `launch_blender.bat` ダブルクリックで起動。スクリプトを直せば保存即反映（再インストール不要）

> 手動インストール: Blender → 編集 → プリファレンス → アドオン → インストール → `scripts/headshrink_addon.py`

## 5ステップで Mod 作成

Blender の Nパネル `HeadShrink` で上から順に進むだけ。

### ① ダンプディレクトリ
- `① ダンプディレクトリ` に `assets/Dump/<Char>`（例 `…/Dump/Yanfei` や `★ok/Yanfei`）を指定
- ディレクトリを選ぶと `②` の `Character` が自動で `Yanfei` に入る（`FrameAnalysis-*` を直接選んだ場合は親名が入る）
- `units` 登録済みなら変更時に自動で `AutoSetup` が走る

### ② キャラメッシュ登録（Units）
- `Analyze Dump` で `(vb0,ib)` ペアを解析、リストに表示。クリックで自動プレビュー
- `表示中のペアを登録` で `MOUTH/EYES/BROW/BODY` に振り分け。`VB` 直入力も可
- セカンダリ口（例 `7a73d3b5`）は **ファイルに書かず毎回自動検出** で済む。手動で `MOUTH` 登録してもOK（`x,y` は後で 0 に正規化される）
- `BODY` は1つ必須、顔は必要なものだけ（`MOUTH` 等）。共有ハッシュでも後述の Body ゲートで他キャラに漏れない

### ③ セットアップ
- `Auto Setup` 1クリックで「全削除 → 選択ペア読込 → プレビュー配置 → ShrinkBox 作成 → `Load Default` 適用」まで自動
- 4つの顔メッシュ（セカンダリ口含む）は `x=0,y=0` に固定、`z` だけキャラ毎に自動計算（中央ズレしない）
- 保存済みの `G` キー微調整があればそれが優先で復元される

### ④ 頭部調整（プレビュー）
- `face_snap_enabled` ON で `G` 移動中に `BODY` 表面へスナップ
- `Reposition Faces` で選択顔だけ再配置（選択なしは全部）
- `shrink_center / half / scale / falloff / shift` と `face_offset_eye/mouth/brow` はリアルタイムで `HS_Preview` に反映
- `Save Char Config` は上書き時に確認ダイアログが出る。`Save Default` は全キャラ共通の基準値として `config.json` の `__default__` に保存

### ⑤ Mod 生成（出力）
- `出力先` は `config.json` の `__global__` にも保存され再起動後も復元
- `Mod Export` で `<Char>BodyPosition.buf`（VB置換） + `<Char><Unit>Base/Key.buf` + `<Char>Head.hlsl` + `<Char>.ini` を出力
- `Body` は `position_vb`（`vs=653c63ba4a73ca8b` のスキニング前バッファ）を置換するためアニメ追従、隙間も出ない。顔は CopyDispatch

出力先例: `G:\XXMI-Launcher-Portable\Mods\Mods\HeadShrink\Yanfei\` → そのまま XXMI の `Mods` に配置してゲームで確認。

## 設定ファイル

- `scripts/config.json`（旧 `face_offsets.json` から自動移行）
  - `__global__`: `dump_dir` / `output_dir`（`launch_blender.bat` と `userpref.blend` の補助）
  - `__default__`: 全キャラ共通の縮小パラメータ
  - `<Char>`: `__config__`（`shrink_*` / `units` / `extra_hashes`）と `Dump_*` の最終 `location`

`dump_dir` / `output_dir` は `NHSAddonPreferences`（`userpref.blend`）と `config.json` の両方に保存される。

## よくあるハマりどころ

**Q. Yanfei の口が Mona/Amber にも効く**
A. 口の `c9846fd5 / 7a73d3b5 (820)` は6キャラ共有。現行は `Body` の `position_vb` ハッシュ（Yanfei `eb8b62d3`）を `[TextureOverrideBodyGate] $is=1` にし、顔は `if $is` でガードする effieface式に自動化してあるため、他キャラでは `Body` が無いので顔も発火しない。`Yanfei` で再 Export すれば直る。

**Q. 全画面に変なテクスチャ**
A. 旧 `auto_extra_hashes` が `vert_count` だけで extra を拾って `deduped` の無関係 820 まで口に混ぜていたのが原因。現行は `(vert_count, vs)` 一致だけで拾うように修正済み。

**Q. `launch_blender.bat` で Blender が立ち上がらない**
A.  symlink 失敗時はエラーで停止するようにした。管理者で実行するか、Windows 設定 → 開発者向け → 開発者モード ON に。

**Q. アドオンエラー `IndentationError` / `bl_info` missing**
A. 旧 `launch_blender.bat` の `echo ... -> ...` がリダイレクトとして解釈され `headshrink_addon.py` を 1行で上書きするバグがあった。`--^>` に修正済み。`git checkout HEAD -- scripts/headshrink_addon.py` で復旧し、再び管理者で `launch_blender.bat` を実行。

## 開発者向け

- 仕様: `.spec/SPEC.md` / TODO: `.spec/TODO.md` / 知見: `.spec/KNOWLEDGE.md`
- テスト: `python -m pytest scripts/test_preview_adjust.py`（181 tests）
- 共有顔の調査: `assets/Dump` を `scan_dump_dir` 相当で横断、共有は `ps-t0` ではなく `Body` ゲートで遮断するのが現状のベストプラクティス

## ライセンス / 謝辞

- 3DMigoto / XXMI-Launcher / WWMI-Tools / effieface の `FaceDiffuse $is` ゲートを参考
- Oodle は RAD Game Tools の `oo2core_9_win64.dll` を使用
