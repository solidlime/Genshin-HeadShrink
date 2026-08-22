# SPEC - 技術仕様・要件定義

## 機能要件
- [x] .blk (Blb3File) → 4段復号 (XOR+AES+RC4+GF256) → Oodle 復号 → Unity serialized
- [x] OodleLZ_Decompress via oo2core_9_win64.dll (Cdecl 14 args)
- [x] AnimeStudio CLI で Unity serialized → OBJ 抽出
- [x] Blender アドオン: 部位別拡縮 + offset スライダー + Render Preview + OBJ 出力
- [x] 全キャラ対応: auto_detect_groups (prefix-based) + JSON prefab override
- [x] **3DMigoto .vb/.ib 変換**: `scripts/build_headshrink_mod.py` — dump + scale parameter → mod フォルダ生成 CLI (position-only modifier, stride 素通し)
- [x] **ワンクリック自動セットアップ** (v1.3.0): dump_dir を有効なディレクトリに変更すると 既存オブジェクト全削除 → 解析 → 自動ペア選択 → インポート → Preview Setup まで自動実行。手動用 Auto Setup ボタンも併設 (2026-08-16)
  - 発火制御: dump_dir update コールバック `_dump_dir_update` — 有効ディレクトリかつ `_last_auto_setup_dir` と異なる場合のみ `bpy.app.timers` (0.1s 遅延) で `headshrink.auto_setup` 実行。同一パスの連続発火は抑制
  - `NHS_OT_AutoSetup`: dump_dir 実在チェック → `bpy.data.objects` 全削除 (do_unlink=True) + HeadShrink_Dump/HS_Preview コレクション削除 → scan → ペア選択 → インポート → Preview Setup (共通化 `_preview_setup_impl`)
  - ゴミペア除外 (select_import_pairs): vert_count 降順ソート走査で「>50000 かつ 次の非顔サイズの 5 倍以上」をゴミとして除外 (除外後にインデックスを戻して再チェック、複数ゴミ対応。Noelle: 911ff708 104857v 除外)。顔サイズ (50..3000) は比較基準にしない。HEAD ロール判定もゴミ除外後の基準
  - head_center_from_verts は NaN ガード付き (math.isfinite 除外、全滅なら None)
- [x] **ハッシュ直接入力 UI** (v1.4.0, 2026-08-16): 3DMigoto ハンティングモード等で取得した VB ハッシュを入力 → units 登録 (HEAD/EYES/MOUTH/BROW/OTHER) → `face_offsets.json` の `__config__.units` に保存 → auto_setup / import_all は units 一致ペアのみインポート (units に無い最大ペアは保険で含む)。いくつでも登録可 — フィールドのみならボディ 1 つ、UI 画面も縮めるなら顔パーツ (目/口/眉) も登録
  - ハッシュ取得方法 (GIMI UsageInstructions より): テンキー 0 でハンティングモード ON → 該当オブジェクトが消えるのでドローを特定 → テンキー 7/8 で IB サイクル・9 でコピー、/ * で VB サイクル・- でコピー。キャラクターメニュー内で実施推奨 (フィールドはオブジェクト過多)
  - ハッシュ値だけでは顔/ボディを区別できない (頭と体は同じ VB/IB で描画、区別は match_first_index)。顔パーツの独立 VB 有無はキャラの実ダンプで確認が必要
- [x] **パネル 4 ステップ構成** (v1.5.0, 2026-08-16): 上から順に進めるワークフロー UI — ① キャラメッシュ登録 (analyze_dump → ペア選択 → units_add_pair で登録、または VB ハッシュ直接入力) → ② セットアップ (dump_dir 指定 → auto_setup 自動実行) → ③ 頭部調整 (shrink スライダー群) → ④ mod 生成 (export_diff)。import_dump/import_all は UI から削除 (auto_setup が包含、クラスは残置)
- [ ] **Eye Box 機能** (v1.7.0, 2026-08-16): 瞳 (BODY メッシュの一部) を Eye Box で範囲指定し、移動/拡縮でスライダー調整
  - Eye Box (HS_EyeBox): ワイヤーフレームボックス (ShrinkBox 方式、別色で区別)。初期配置は白目 (EYES) の bbox に自動配置 (瞳は白目の中央にあるため)。G キー移動 / S キー拡縮 → Apply Eye Box Position で反映。中心/サイズは props (`eye_box_center` / `eye_box_half`) に保存
  - スライダー (Step 4 頭部調整): Eye Move X/Y/Z (eye box 内の BODY 頂点を各軸方向に移動) + Eye Scale (eye box 内の BODY 頂点を eye box 中心から均一拡縮)
  - 適用: プレビュー更新時、BODY メッシュの頂点のうち **eye box 内 (3D bbox 内、x/y/z 全部)** に入るものだけ移動/拡縮。**EYES (白目) は対象外** (瞳は BODY メッシュに含まれる。まぶた・皮膚も eye box 外なので対象外)
  - eye_sink (凹み) は既存のまま共存
  - 保存: Save Char Config / Load Char Config で eye box 位置 + スライダー値を保存
  - mod 出力: プレビュー座標がそのまま Key.buf に反映 (既存仕組み、追加実装なし)
- [ ] **ゲーム dump 取得**: xxmi-tools / 3dmigoto dump 環境構築 (T002 着手前提)
- [ ] **.ini 実ゲームでの hash 整合確認**: XXMI-Launcher で mod 適用テスト

## v2.0.0 仕様 (2026-08-17, 設計承認済み: docs/superpowers/specs/2026-08-17-headshrink-v2-design.md)
- [ ] **顔メッシュのプレビュー配置 (draw_vb → position_vb 空間の近似変換)**: BODY は position_vb 空間 (直立)、顔メッシュは draw_vb 空間 (ポーズ) のまま表示し、BODY 頭部に自動配置。方式 = 最近傍スキニング変位加算: 各顔頂点 p に対し BODY draw_vb の最近傍頂点 i を探索し p' = p + (body_pos[i] - body_draw[i])。配置 loc = 境界ペア (距離 < 閾値) の位置差の中央値 (既存 _match_face_offsets の手法を流用)。顔メッシュの v.co は draw_vb 空間のまま、変換は obj.location で表現 → export は v.co だけで完結 (loc と独立)
- [ ] **box/pivot 整理**: pivot (縮小中心) = box 中央固定 (v1.7.1 相当)。_auto_face_pivot の自動設定を削除し、_preview_props_update / NHS_OT_PreviewApply は origin = shrink_center。_body_head_bbox は box 初期配置のみに使用。UI の shrink_origin 行は削除 (プロパティは互換残置)
- [ ] **顔メッシュの縮小中心 = 顔メッシュ自身の中心**: 顔メッシュの全頂点変形は表示空間 bbox 中心 (hs_original_pos + loc) 基準。BODY は box/pivot (box 中央) 基準のまま
- [ ] **プレビューと mod 出力の分離保証**: export はプレビューの loc を一切使わない (BODY: display_to_position_vb(v.co)、顔: display_to_game(v.co))。顔メッシュの縮小は draw_vb 空間の v.co に対して行う
- [ ] バージョン (2, 0, 0)

## 非機能要件
- **パフォーマンス**: .blk 41MB 全体を復号しても数十秒以内
- **互換性**: Blender 5.2.0 LTS / Python 3.12 / Windows
- **拡張性**: 任意キャラ mesh に対して、JSON 1ファイル追加で対応可能

## 技術構成
- **言語**: Python 3.12 (scripts/), Blender Python (addon)
- **主要依存**: lz4, UnityPy 1.25.3, ctypes
- **外部ツール**: AnimeStudio CLI (`D:\Tools\AnimeStudio\`), Blender 5.2.0, XXMI-Launcher, oo2core_9_win64.dll (RAD Game Tools), 3DMigoto
- **対象ゲーム**: 原神 (Genshin Impact) — StreamingAssets/AssetBundles/blocks/00/

## パイプライン全体像

```
[Game StreamingAssets/00/<hash>.blk]
    ↓ AnimeStudio CLI (Blb v3 → Unity serialized)
    ↓ UnityPy + oo2core_9_win64.dll (Oodle 復号)
[抽出 OBJ (Blender プレビュー専用)]
    ↓
[Blender アドオン: headshrink_addon.py — 拡縮パラメータ決定]
    ↓ headshrink_props (FloatVectorProperty size=18)
[JSON spec: groups / vertex_range / ib_range / target scale]
    ↓
[3DMigoto dump (ゲーム起動 + 3DMigoto d3d11 hook)]
    ↓ Position.buf / IB.ib / Blend.buf / TexCoord.buf / hash.json
[scripts/build_headshrink_mod.py]
    ├-- scale positions (only xyz, stride 素通し)
    ├-- split IB (match_first_index 境界)
    ├-- generate <Char>.ini (TextureOverride + Resources)
    ↓
[Mod folder: DisableIB/<Char>/...]
    ↓ XXMI-Launcher に配置
[ゲーム内で head shrink 適用]
```

### 重要: OBJ はプレビュー専用
- game dump (Position.buf + IB.ib ペア) が必ず別途必要
- build_headshrink_mod.py は dump 必須。OBJ → .vb 直接変換は不可 (UV/normals/blendIdx/hash 情報欠落)

## データ構造・インターフェース

### mesh グループ JSON (`scripts/prefabs/<char>.json`)
```json
{
  "char_name": "Nilou",
  "groups": {
    "HEAD":  {"description": "head area", "names": ["Face", "Brow", "Mask", ...]},
    "BODY":  {"description": "body",      "names": ["Body", "Body_LOD1", ...]},
    "EYE":   {"description": "eyes",      "names": ["Pupil", "EyeStar"]},
    "BANG":  {"description": "front fringe", "names": ["Bang", "Bang_LOD1", ...]},
    "EFFECT":{"description": "effects",   "names": ["EffectMesh", "EffectHair"]}
  }
}
```

### groups_spec.json (build_headshrink_mod 用, 複数ユニット対応)
```json
{
  "index_bytes": 2,
  "units": [
    {
      "name": "Body",                     // ユニット名 (空=メイン)。ファイル名接頭辞に使う
      "position": "def7af36",             // ダンプ vb0 ハッシュ
      "ib": "9cf0789e",                   // ダンプ ib ハッシュ
      "vert_count": 15965,
      "groups": [
        {"name":"Head", "vertex_range":[0, 4299],     "ib_range":[0, 12915]},
        {"name":"Body", "vertex_range":[4299, 15965], "ib_range":[12915, 50502]}
      ]
    },
    {
      "name": "Eyes",                     // 顔独立 VB (UI 画面用)
      "position": "63f702ce",
      "ib": "0bcb587f",
      "vert_count": 1083,
      "groups": [
        {"name":"Head", "vertex_range":[0, 1083], "ib_range":[0, 4290]}
      ]
    }
  ]
}
```
- 旧形式 (単一 unit: `vert_count` + `groups` 直下) は後方互換で受け付ける
- `index_bytes` 2=16bit / 4=32bit。実ダンプは 16bit (R16_UINT) が標準
- `--scale HEAD=0.65` は全ユニットの同名グループに適用 (顔も一緒に縮む)

### dump ディレクトリ (build_headshrink_mod 入力, フレームダンプ直接対応)
- フレームダンプ形式 (`NNNNNN-vb0=<hash>-vs=...-ps=....buf`) から
  `NNNNNN-vb0=<hash>` / `NNNNNN-ib=<hash>` で該当フレームを検索して読む
- `hash.json` — `{position, ib, blend, texcoord, vertex_limit}` game-internal hashes
  (フレームダンプ時はファイル名のハッシュから自動導出、実体指定も可)

### Blender アドオン UI (NHSProps)
- `mesh_dir: StringProperty (DIR_PATH)`
- `output_dir: StringProperty (DIR_PATH)`
- `prefab_name: EnumProperty (Auto / Nilou / Mitya / Tighnari)`
- `group_scales: FloatVectorProperty (size=18, 6 groups × XYZ)`
- `group_offsets: FloatVectorProperty (size=18)`

### 3DMigoto 出力 (build_headshrink_mod 実装済, Bennett 準拠構造)
- `<Char><Unit>Position.buf` — vertex buffer (40B/vert 原神標準、position 12B のみ scale)
- `<Char><Unit>Blend.buf` — bone weights (passthrough, unit 別 blend_stride: 本体 20B / 顔 12B)
- `<Char><Unit><Group>.ib` — group 分割 IB (**常時 R32_UINT 変換**, to_r32_ib)
- `<Char>.ini` — Bennett 実物 (GameBanana 674758) 準拠:
  - `[Constants] global $active = 0` (1回, 先頭) + `[Present] post $active = 0` (末尾)
  - 各ユニット: Position (hash=vb0, vb0=Resource, $active=1) / Blend (hash=vb1, handling=skip, vb1=Resource, draw=vert_count,0) / IB (hash=ib, handling=skip のみ) / 各 Group (hash=ib, match_first_index, ib=Resource, drawindexed=count,0,0)
  - Resources: Position stride=40 / Blend stride=unit別 / IB format=DXGI_FORMAT_R32_UINT
  - **VertexLimitRaise は生成しない** (vb0 と同一 hash にするとフリーズ。正規は draw_vb の別 hash が必要なため)

### 重要な診断結果 (2026-08-16, 3 症状: 点滅/アニメ破綻/UI フリーズ)
- **顔独立 VB (U1-U3) の VB/IB 置換はコミュニティに前例のない非正規パターン**。動作実績 mod は全て「体のみ VB/IB 置換、顔はテクスチャ差し替え or CopyDispatch HLSL」
- 顔 hash はキャラ間共有 → 他キャラの顔ドローに誤マッチして点滅/破綻
- UI 画面は同じ IB を細切れドロー+アニメで使用 → match_first_index=0 前提の置換が衝突してフリーズ
- **現行 mod は U4 (本体) のみで構成**: HEAD (頭部髪+顔頂点 0..4300) / BODY / ACCESSORY (小物カバー)
  - フィールドの顔は U4 HEAD グループに含まれる頂点 0..1082 で縮小済み
  - UI 画面の顔縮小は未対応 (正規方式は後日 T002-d で検討: $faceScale+OffsetFace or effieface 方式)
- **グループ未定義の IB 範囲は skip されたまま再発行されず消失する** (小物消失) → アドオンが `fill_uncovered_accessories()` で自動補完 (ACCESSORY/ACCESSORY2...)
- デバッグ: `Mods\d3dx.ini` [Logging] calls=1 で `Mods\log.txt` に TextureOverride マッチ記録。調査後 calls=0 に戻す

### 隙間バグ調査の経緯と結論 (2026-08-16〜17, v1.6.7〜v1.7.3)
- 症状: 縮小反映 mod で顔メッシュとボディの間に隙間 (顎ライン・目口眉の段差・瞳が白目に埋まる)。フィールド/UI 両方で発生、縮小率に比例 (0.5 縮小で倍増)
- 対応履歴:
  - v1.6.7: export 補正 (1-s)*loc 加算 + shrink_origin 自動設定 (顎ライン) → **補正は逆効果** (境界 gap 0.038 新造、analyze_gap2 の数値比較で証明)
  - v1.6.8: 誤補正撤去 (export を v1.6.6 相当に戻す)
  - v1.6.9: shrink_origin.y/z 自動設定 → 境界 gap に影響なし (face/body 共通中心縮小のため)
  - v1.7.0: **境界マッチング** (`_match_face_offsets`、headshrink_addon.py:1405) — 顔メッシュ配置 loc を body 境界との最近傍位置差中央値で収束計算。face_offsets.json の Noelle loc の y が 0.06-0.09 誤差だったのを修正 (EYES (-0.0195,-0.0372,0.3646) 等)
  - v1.7.1: 縮小中心を box 中央 (shrink_center) に固定 (shrink_origin 自動設定廃止、ユーザー「box 中央に縮小」が自然という指摘)
  - v1.7.2: auto_setup が保存済み shrink パラメータを上書きしないよう修正 (apply_char_config 呼び出し削除)
  - v1.7.3: 顔メッシュは常に全頂点変形に固定 (face_full_transform チェック廃止)
- 確認済み事実: CopyDispatch + base/key は正規方式 (effieface/Bennett 実物と HLSL 同一)。Noelle 4 ユニットの頂点数は IB と完全一致 (Reorder 不要)
- **残課題 (未解決)**: ゲーム内での隙間が完全には消えていない。候補は ① DCR (Dynamic Character Resolution) 有効 (GIMI Issue #364 公式認定の freaky geometry、無効化確認が次の一手) ② フィールドの隙間 = box 境界の段差 (顎が box 縁付近) ③ UI 画面 = 頭部回転ドリフト + カットシーン用第 2 ハッシュ不足 + diffuse ガードなし。詳細は KNOWLEDGE.md「CopyDispatch 顔変形の正規ワークフロー」参照
- v1.7.4 (2026-08-17): 縮小中心を顎ラインに自動設定 (_auto_face_shrink_center、auto_setup 時に顔メッシュ bbox 下端へ) + falloff 0.3。ゲーム確認で「これまでで一番マシ」まで改善。残る僅かな隙間は center 微調整で詰める方向
- v1.8.0/1.8.1 (2026-08-17): ベネット式 VB 置換 export モード (BODY = ダンプ vb0 の position のみ差し替え、normal/tangent 維持。顔は CopyDispatch のまま = ハイブリッド) + 旧ファイル掃除
- v1.9.0/1.9.1 (2026-08-17): position_vb (スキニング前静的バッファ、pointlist パス vs=653c63ba4a73ca8b の vb0) を自動認識して BODY の import/export を切替。毎フレーム再スキニングされるためアニメ追従 + 隙間ゼロの原理。座標系: position_vb = y-up モデルローカル (display = (-lx, -lz, +ly))。draw_vb 置換はアニメ静止の原因 (v1.8.0 初版で実証)
- v1.8.0/1.8.1 (2026-08-17): ベネット方式完全模倣 — BODY = vb0 (Position) 直接置換 (スキニング前バッファ差し替え、アニメ完全追従で隙間ゼロの原理) + 顔 = CopyDispatch 維持 (ハイブリッド)。export_mode (VB_REPLACE default)。export 時に旧ファイル掃除

### 口つぶれ・チーム画面隙間の解析 (2026-08-22, NG dump FrameAnalysis-2026-08-22-2010)
- 症状: ①mod 再出力後に口メッシュがつぶれる (Noelle/Sucrose) ②チーム編成画面で無関係キャラの口・目に隙間
- **根因 A: 顔パーツ CopyDispatch HLSL が非冪等**。`rw_buffer[DTid.x].position += key[DTid.x].position - base[DTid.x].position` の累算式で、同一 bind に一致するセクションが複数回実行されると N 回適用 = N 倍縮小 → つぶれ/部品剥離 → 隙間。hlsl は全キャラ同一内容 (MD5 96DB33FD...)
- **根因 B: 顔パーツ VB ハッシュが同体型キャラ間で共有**。口 6192fe1c+d265427c は Noelle.ini と Sucrose.ini の双方に存在 (他: Furina/Lynette/Nilou efa4da64+5c536604、Furina/Lanyan/Mizuki f4d23e3c、Barbara/Sucrose brow 2cfd04ad、Lynette/Yanfei 9c75320a、Barbara/Kokomi/Yanfei 口 c9846fd5+7a73d3b5)。$is は ini ファイル単位で独立なため、ソロ表示では事実上の排他として働くが、同時表示では全員のゲートが発火し共有ハッシュに人数分 Δ が加算される
- 対応方針: P1 = HLSL 冪等化 (距離比較で cur≈key なら skip / cur≈base なら適用、生成テンプレ変更で全キャラに効く) / P2 = オフラインテスト (二重・三重適用 = 1 回分を検証) / P3 = チーム画面ダンプで代替仮説「ゲートレース (自分のゲート発火前に顔パーツが描画されスキップ→無縮小)」の有無を確認
- **P3 検証完了 (2026-08-22, 編成画面ダンプ FrameAnalysis-2026-08-22-212336)**: 根因 A+B を実証
  - 同一フレーム同一シェーダー重複 Dispatch 32件。Frame 234/240/258/264 は NoelleMouth×2 + SucroseMouth×2 (共有口ハッシュに 4 回 Δ)。Frame 237/243/261/267 は FurinaMouth + NilouMouth_5c536604 が連鎖
  - メカニズム: 同一 bind に一致する全 ini のセクションが順次実行され、2 個目以降は改変済み dif を copy するため Δ 累算。$is は ini 単位のため画面内全員のゲートが上がると人数分適用
  - 口バッファの Map は frame 1 のみ (以後ゲームからの再アップロードなし)
  - ゲートレース仮説は棄却: `if $is: false` 40件は全て画面外キャラ (Lynette/Lanyan/Mizuki/Barbara/effieface)
  - 「隙間」の正体は過剰縮小による目・口メッシュの剥離。ソロで無症状なのは自分の ini の $is しか上がらないため
- 参考: 「たまにズレ」は別根因 — 口 VB ハッシュが表情状態で 6192fe1c ⇄ d265427c に切替わるためで、auto_extra_hashes による変種セクション自動追加で対応済み (v1.9.x)

### 点滅バグの解析と T015 設計判断 (2026-08-22, dump FrameAnalysis-2026-08-22-230007, #081 判断済み)
- 症状: T014 冪等化 HLSL で Noelle のみ再エクスポート後、口・目・眉が常時点滅 (拡大⇔縮小交互)
- 根因 1 (cross-char 連鎖): 共有顔ハッシュに NoelleMouth(冪等版 k_N 適用) の直後 SucroseMouth(旧非冪等 += 版) が同一 bind で連鎖し過剰変形。$is は ini 単位だが SucrosePosition(b655c335) が frame3 にバインドし彼女の $is も上昇 → 同時有効は通常プレイで常態
- 根因 2 (ゲート間欠): gate(def7af36) はリソース再バインド時しか発火しない。142 フレーム中顔セクション実行は burst 窓のみ (f19-27 ×1dispatch, f55-63 ×2dispatch)。skip フレーム = 無縮小描画 → 処理フレーム⇔skipフレームの交互が点滅
- 観測: f88-140 に未知ハッシュ aa41c13a (112992B) が 53 フレーム連続描画 (未カバー variant/LOD 疑い、未確定)
- **T015 設計判断 (#081 案A採用)**: 共有顔ハッシュ (顔 UI ユニット: 目/口/眉 role + variant) の Key = Base を顔メッシュ自身の中心で純スケールしたもの (配置移動なし、Key = f(Base, scale) の純関数)
  - 根拠: 同一ハッシュ = 同一バッファ = 一つの変形のみ可能。per-char 移動は cross-char 共有下で原理的に不可能 (案B 正規代表キャラ方式は「非正規キャラの顔が正規キャラ頭部位置に飛ぶ」を仕様化するだけ)。Key=f(Base) なら全キャラ Key.buf バイト一致・決定論が構造的に保証・エクスポート順序非依存
  - 代価: T011/T012 の顔配置移動を共有ハッシュ分は放棄 (UI 画面での密着感が若干退化)
  - (b): IB ハッシュセクション (handling=skip, 毎ドロー発火) にも $is=1 追加 → ゲート確実化。BodyGate(def7af36) は残置 (冪等・IB 差し替え環境のフォールバック)
  - **BLOCKER 制約: (a)(b)(c) は同時リリース必須** — 旧非冪等 ini が一つでも残る状態で IB ゲート毎フレーム発火させると += 連鎖が加速する。全キャラ再エクスポート完了まで点滅解消を検証しないこと

## Noelle 実ダンプ構成 (2026-08-15 検証済み, FrameAnalysis-2026-08-15-222105)

| パーツ | VB hash | IB hash | 頂点数 | 備考 |
|--------|---------|---------|--------|------|
| 本体 (頭髪+体+小物) | def7af36 | 9cf0789e | 15965 | IB 3分割 [0:12915)=頭部髪 / [12915:47910)=体 / [47910:50502)=小物 |
| 目周り (UI用独立) | 63f702ce | 0bcb587f | 1083 | stride 40, ic=4290, start=0 base=0 |
| 口周り (UI用独立) | 6192fe1c | 3049e662 | 877 | stride 40, ic=4014, start=0 base=0 |
| 眉 (UI用独立) | ddf54429 | da7f6805 | 56 | stride 40, ic=156, start=0 base=0 |

- 全 IB 16bit (R16_UINT)。ドローは全て start=0 base=0 で全 index 使用
- フィールドでは顔 IB (0bcb587f/3049e662) が本体統合 VB def7af36 の先頭頂点 (0..1082/0..876) を参照して描画 → **統合 VB の頭部頂点縮小でフィールドの顔も一緒に縮む**
- UI 画面 (選択/装備/図鑑) は独立 VB を使用 → 顔パーツの TextureOverride を別途生成する必要あり
- 顔 3 パーツの縮小 = 全頂点縮小 (全て頭部領域) なので scale のみ適用、IB 分割不要

## T016: dump dir 再オープン時の unit リストリセット廃止 (2026-08-23)

**症状**: dump dir を開きなおす（同じパスを再選択するだけでも）unit リスト (units_list) がクリアされる。Blender 再起動時も prefs 復元の代入で update が発火し同様にクリアされる。

**根因** (`_dump_dir_changed` L1855-1876):
- L1871-1872 がキャラ判定と無関係に無条件で `units_list.clear()`。コメントは「キャラ切替とみなし」だが同一キャラ再オープンでも発火する。
- register() の load_global_dirs 復元 (L4138-4141) も保存値が初期値と異なる限り必ず update 発火 → 起動のたびにクリア。

**設計判断**:
- unit リストの永続層は config.json (`__config__.units`) でありクリアしてもデータは失われないが、UI 再登録の手間が無駄。
- クリアが必要なのは「キャラが実際に切り替わった時」だけ。同一キャラでの再オープン・起動時復元ではリストを保持する。

## T017: 点滅恒久対応 — HS_EPS 恒久化 (2026-08-23, 実機検証済み)

**根因確定 (仮説D)**: 表情バリアント高速交替 × 冪等EPS判定失敗。口VBは口パクで `6192fe1c ⇄ d265427c` が高速切替されるが、variant 内容は元 dump と最大 ~6e-4 ずれるため `HS_EPS=1e-4` では variant 適用時に `cur≈base` 不成立 → noop → **縮小⇔原寸が口パク周期で交互 = 高速チラつき**。目・眉も同様のバリアント対で同症状。

**実機検証**: SucroseHead.hlsl の EPS を手動で 5e-3 に変更 → ユーザー確認で点滅解消 (フィールド/UI両方)。

**決定 (ユーザー承認)**: EPS を **5e-3 に恒久化**。
- 根拠: 実機実証済み・最小diff。観測最大 variant 差 (~6e-4) の約8倍のマージン。
- 既知の上限: variant 差 > 5e-3 のバリアントが出現したら点滅が再発する (その場合は variant 専用 Base/Key 生成 = 完全版へ移行)。
- 代価: 5mm 未満の微小頂点移動は skip されうる (#081 評価: 視覚影響軽微)。

## T018: face offset 復活 — キャラ毎 Key への配置移動再導入 (2026-08-23, #081 GO)

**背景**: T015 案A で FACE UI Key から配置移動を除去した結果、face_offset_eye/mouth/brow プロパティが効かなくなった。ユーザーが代価を明示的に拒否 (#081 案Aからの部分撤回が決定)。

**[Present] 謎の解決**: 生 log.txt 直接 grep の結果、`[Present]` 行は F1/F163 (キャプチャ境界フレーム) にしか記録されない = FA ログはコマンドリスト命令を毎フレーム記録しない構造。以前の「$is がずっと 1」説はログアーティファクト。$is ライフサイクルは設計通り動作と結論 (lib-1 ソース読みと整合)。

**設計 (#081 GO)**:
- `_face_key_verts` に `offset` 引数追加 (デフォルト `(0,0,0)`)。role→prop 解決 (`_FACE_OFFSET_PROPS`) は呼び出し側の責務
- **offset は display 空間プロップなので game 空間へ `display_to_game(offset)` 変換してから加算すること (最重要・#081 指摘)**
- 冪等 HLSL 維持。共有 bind 上では先勝ち (2番手以降 noop、スタックしない = T014 成果維持)
- variant セクションは Base/Key 共有により自動的に offset を継承。EPS 5e-3 > variant ドリフト ~6e-4 で点滅修正と干渉なし
- **既知制約 (受入済み)**: チーム画面等の同時表示では、共有顔パーツがセクション名アルファベット順の先勝ちとなり、非先行キャラの顔パーツが先行キャラのオフセット位置に寄る。ソロプレイでは完璧

## リファクタリング仕様 (2026-08-22, #081 アーキテクチャ判断済み)

### 方針
- **単一ファイル内再構成を採用。インストール機構 (launch_blender.bat 単一ファイル symlink) は凍結**
- 理由: ①test_preview_adjust.py が `import headshrink_addon as hs` 単一モジュール前提 (Fake bpy 注入) ②病因は行数ではなく関数レベルの肥大 (extract-method で完治) ③bat 改修リスク > 分割利益
- モジュール分割の引き金: 「6k行超え」「複数人開発」「テスト実行時間劣化」のいずれかが来た時
- セクション契約 (明示的境界コメントで固定): [1] bl_info/imports/定数 → [2] 純関数層 (bpy非依存: dumpスキャン/数学/INI生成/hash解決/config永続化) → [3] role分類ヘルパー → [4] PropertyGroup宣言 → [5] updateコールバック (薄いアダプタのみ、本体は _impl 純関数) → [6] UIList/Prefs → [7] Operators (execute は orchestrator、ロジックは impl へ) → [8] Panel/register
- **原則: [2][3] に bpy を持ち込まない** (将来の機械的分割可能性を保証)

### やらないこと (YAGNI)
- NHSProps の PropertyGroup 分割 — bpy property path が userpref.blend/.blend に永続化されるため全ユーザー設定喪失リスク。アクセス経路整理のみ
- DI / Operator 抽象基底クラス / props の dataclass ミラー / プラグインレジストリ — 不要
- 全面型ヒント付与 — 触った関数のみ

### 安全策
- Phase 3 着手前に **golden master テスト** 凍結: フィクスチャ dump に対する INI 出力と config JSON をバイト一致比較。1バイトでも変われば BLOCK
- update コールバックのシグネチャ `(self, context)` は絶対不変 (Blender RNA 制約)。中身の抽出のみ
- 手動スモーク checklist (Phase 3-4 ごと): Analyze Dump → Preview Setup → slider 調整 → Preview Apply → Export Diff → XXMI で mod 実確認
- git 衛生: 1 phase = 1 commit、着手前にタグ
