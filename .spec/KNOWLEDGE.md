# KNOWLEDGE - ドメイン知識・調査結果

## 業務・ドメイン知識
- 原神のキャラ 3D モデルは StreamingAssets/AssetBundles/blocks/00/*.blk に格納
- miHoYo は独自暗号化: XOR + 改造AES + カスタムRC4 + GF256 (4段)
- 配布 mesh の type tree が剥がされていて Unity bone weights が取得不可 (TypeHash MD5 のみ)
- SkinnedMeshRenderer (ClassID 137) は Nilou では 0 件 — Avatar (Humanoid rig) + AnimatorOverrideController で骨管理
- MdbComponent (ClassID 1152437153) は複数のプレイアブルキャラで使われている独自形式

## 調査・リサーチ結果
- **Escartem/AnimeStudio** (https://github.com/Escartem/AnimeStudio, 1079★, 2026 update): .blk → Unity serialized 変換 CLI。唯一の現役ツール。
- **khang06/genshin-studio**: ❌ 2024 削除 (Wayback なし)
- **radioegor146/GenshinStudio**: classID 難読化デコード式のリファレンス実装
- **Oodle**: RAD Game Tools 提供の Kraken 系圧縮。`oo2core_9_win64.dll` の `OodleLZ_Decompress` (Cdecl, 14 args) を利用
- **3DMigoto**: XXMI-Launcher 同梱の mod framework。TextureOverride.ini で hash match → vertex/index buffer override

## 技術的な知見

### 4段復号アルゴリズム
```
blk header (28B)
  → blocksInfo: XOR (2-byte key per 16-byte block) → AES-CBC → RC4 → GF256 表引き
  → block_data: OodleLZ 圧縮
  → Unity serialized (CAB + SerializedFile)
```

### クリティカルバグ (既に修正済)
`scripts/blb_parser.py:81` で `size = i32()` がノードループ内で外側 `size` を上書き（shadowing）。
→ 修正: `node_size = i32()` に rename。修正前は `self.block_data_offset` が完全にずれた位置を読んで garbage 取得。

### Blender addon 設計判断 (ponytail)
- `FloatVectorProperty(size=18)` — 6 グループ × XYZ を 1 プロパティに詰める。Blender RNA のサイズ上限は実機でのみ確認可能。
- グループ→スロット mapping は module-level キャッシュ (`(mesh_dir, prefab_name)` → groups) で管理。Scene に死に状態を持たせない最小構成。
- old addon (`nilou_headshrink_addon.py`) → `headshrink_addon.py` に rename。`op_id` は `headshrink.*` に統一（後方互換性なし、Blender 側で旧アドオン無効化推奨）。

## 決定事項と理由

### MESH_GROUPS → JSON prefab + auto-detect
- **採用案**: hybrid — prefix 自動検出 (default) + JSON prefab override
- **理由**: Nilou/Mitya/Tighnari で mesh 名パターンがほぼ同じ（`Body*`, `Face*`, `Brow*`, `Bang*`, `Pupil*`, `Mask*`, `Effect*`）。prefix 自動検出で 90% はカバー、残りは JSON で外出し。
- **他案不採用の理由**:
  - 完全手動 JSON: 全キャラ分の JSON が必要、運用コスト高
  - 完全 auto-detect のみ: 特殊衣装（瞳違い等）の対応が結局 JSON 必要になる

### OBJ 出力フォーマット
- 現状: `mesh.from_pydata(verts, [], faces)` — normals/uvs なし、triangulate 強制
- トレードオフ: bone-aware shrink するなら Mesh binary parser 自作が必要だが、bone-aware でなくても head shrink 0.65 は視覚的に十分機能する

### アドオン名の改名タイミング
- 旧 `Nilou Head Shrink` → `HeadShrink` にリネームするタイミングでディレクトリ名変更と一致させた
- 一貫性: ディレクトリ名・アドオン名・GitHub リポジトリ名 (将来) は全て同じにする

### Auto Setup (v1.3.0) 設計知見
- **ゴミペア判定基準**: ダンプには 104857v 級のゴミ VB (911ff708) が混入する。判定は「>50000 かつ 次の非顔サイズの 5 倍以上」で除外を繰り返す。顔サイズ (50..3000) は比較基準にしない (顔が次点になるのを防ぐ)。「10 倍」では複数ゴミ連続時に 1 個目だけ除外で止まるため 5 倍 + インデックス戻しで再チェック
- **hs_role 自動判定の限界**: role_for_pair は units_map (char config) 優先 → 未保存時は最大=HEAD、他は全部 OTHER。目・口・眉はユーザーが UI で再タグ付けして char config 保存する運用 (まだ config 未保存)
- **bpy.app.timers と MCP**: execute_blender_code 内で time.sleep してもタイマーは回らない (メインループ停止)。検証は呼び出しを分離して行う。実機では呼び出し間のアイドル中に発火する
- **update コールバック内で bpy.ops 直接呼びは再入リスク** → 0.1s タイマー経由 + `_last_auto_setup_dir` で連続発火抑制 (同値設定の再発火防止)
- **サブエージェント検証の教訓**: fixer の完了報告は信頼せず必ず MD5 変化 + シンボル grep + テスト実行で実体検証する (1 回目は「完了」と報告しながらファイル無変更の虚偽報告があった。同一 task_id で resume し再委譲で解決)

### ハッシュ入力 UI (v1.4.0) 設計知見
- **units は「いくつでも登録可」のホワイトリスト設計**: フィールドのみならボディ 1 つ、UI 画面も縮めるなら目/口/眉も登録。units_save は load_char_config で既存 config 取得 → units キーだけ更新 → save_char_config (face offsets と他キー無傷)
- **ハッシュ取得方法 (GIMI UsageInstructions 調査)**: テンキー 0 でハンティングモード (該当ドローが消える) → テンキー 7/8 で IB サイクル・9 でコピー、/ * で VB サイクル・- でコピー。キャラクターメニュー内実施推奨 (フィールドはオブジェクト過多)。フレーム解析ダンプ (F8) は数 GB 級で密集地クラッシュ注意
- **ハッシュ値だけでは顔/ボディを区別できない** (GIMI ガイド明記): 頭と体は同じ VB/IB で描画され、区別は match_first_index による index 範囲指定。顔パーツ (目/口/眉) の独立 VB 有無はキャラ実ダンプで確認が必要。原神はキャラを最低 6 バッファに分割 (position/blend/texcoord/毎フレーム描画用/index×2-3)
- **Blender MCP での report({'ERROR'}) は RuntimeError として伝播** (実機 GUI ではステータスバー表示のみで中断しない)。MCP 経由の検証コードでは無効入力のオペレータ呼び出しが例外で止まる点に注意
- **NHS_PT_panel は poll 未定義** (常時表示)。draw 検証は MockLayout + SimpleNamespace(scene=...) で可能
