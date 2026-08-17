# HeadShrink v2.0.0 設計・実装プラン (2026-08-17)

## 背景

ユーザーの目的 (7 項目):
1. 原神キャラの顔縮小 mod を作りたい
2. 膨大なキャラがいるので Blender アドオン (メッシュ変形アドオン) で時短したい
3. ダンプファイルから体メッシュ・顔メッシュを抽出し、立った状態で配置すること
4. 体メッシュと顔メッシュはキャラクターとして成立するモデル形状、つまり正しい位置に配置すること
5. Blender で縮小率・縮小範囲をリアルタイムプレビューしながら指定できること
6. Blender プレビューとゲーム内プレビューを一致させる
7. mod 生成ボタンでプレビュー状態をゲーム内に反映できる mod を出力すること

## 設計決定 (brainstorming 承認済み)

1. **mod 出力 (ゲーム内)**:
   - BODY = position_vb 置換 (スキニング前の静的位置バッファを縮小済みで置換 → ゲームが毎フレーム再スキニング → アニメ追従 + 隙間ゼロ)
   - 顔独立 VB (目・口・眉) = CopyDispatch のまま (position_vb が存在しないため VB 置換不可能、ベネット実物も同じ構成)
2. **プレビュー (Blender)**:
   - BODY = position_vb 空間 (直立) で表示
   - 顔メッシュ = draw_vb 空間 (ダンプ時ポーズ) のまま表示し、BODY 頭部に自動配置 + 手動調整で重ねる
   - **プレビューの配置 (loc) は mod 出力に一切影響しない (完全分離)**
3. **縮小パラメータ**:
   - box = セットアップ時に BODY 頭部へ初期配置するだけ、以後は完全にユーザー手動
   - pivot (縮小中心) = box 中央に固定 (box を動かせば縮小中心も動く)
   - 顔メッシュ = 全頂点変形 (box 外でも縮小)、縮小中心は顔メッシュ自身の中心
4. **パネル**: 現在の 5 ステップ構成 (① ダンプディレクトリ → ② キャラメッシュ登録 → ③ セットアップ → ④ 頭部調整 → ⑤ mod 生成) を維持

## 座標系の整理 (現状確認済み)

| データ | 空間 | 変換 |
|---|---|---|
| position_vb (BODY) | y-up モデルローカル (直立、z 0..1.6) | position_vb_to_display(p) = (-p.x, -p.z, +p.y) |
| draw_vb (BODY/顔) | game 空間 (ポーズ、x-down) | game_to_display(p) = (p.z, p.y, -p.x) |
| display → position_vb | | display_to_position_vb(p) = (-p.x, +p.z, -p.y) |
| display → game | | display_to_game(p) = (-p.z, p.y, p.x) |

## 実装項目

### 1. 顔メッシュのプレビュー配置 (draw_vb → position_vb 空間の近似変換)

顔メッシュは draw_vb 空間 (ポーズ) で、BODY は position_vb 空間 (直立)。プレビューで重ねるため、顔メッシュを position_vb 空間に近似変換する。

**方式: 最近傍スキニング変位加算**
- BODY の draw_vb (def7af36) と position_vb (d1384d15) は同じ頂点数 (15965) で頂点順序対応 (両方ダンプから取得、同一フレーム)
- 各顔メッシュ頂点 p (draw_vb 空間) について、BODY draw_vb の最近傍頂点 i を numpy k-d tree (scipy 使用 or 自前) で探索
- p を position_vb 空間へ: p' = p + (body_pos[i] - body_draw[i]) (スキニング変位を加算)
- 顔メッシュ全体の配置: loc = 全頂点の (p' - p) の平均 (代表並進) — ただし局所変位が残るため、メッシュ全体の平均でなく「境界ペアの位置差の中央値」を使う (既存 _match_face_offsets の手法を流用)

**実装**:
- `_face_draw_to_body_space(face_mesh, body_draw_verts, body_pos_verts)` 新規関数: 最近傍探索で変換
- `_preview_setup_impl`: 顔メッシュの配置をこの変換で計算 (現状の head_center - face_center から置換)
- 顔メッシュの頂点座標 (v.co) は draw_vb 空間のまま、変換は obj.location で表現 (→ export は v.co だけで完結、loc と独立)

### 2. box/pivot の整理

- `_auto_face_pivot` の自動設定を削除 (pivot = box 中央固定に戻す、v1.7.1 相当)
  - `_preview_props_update` / `NHS_OT_PreviewApply`: origin = shrink_center に変更
  - `_body_head_bbox` は center/half の初期配置にのみ使用 (pivot には使わない)
- box 初期配置: `_auto_face_shrink_center` 維持 (auto_setup 時のみ BODY 頭部へ)
- UI: shrink_origin (pivot) プロパティ行を削除 (v1.7.1 と同じく互換残置)

### 3. 顔メッシュの縮小中心 = 顔メッシュ自身の中心

- 顔メッシュの全頂点変形は「顔メッシュの表示空間 bbox 中心」基準に変更
  - 新関数 `_face_mesh_center(mesh)`: 顔メッシュ (loc 適用後の表示位置) の bbox 中心
  - `_preview_props_update` / `NHS_OT_PreviewApply`: 顔メッシュは `preview_shrink_mesh(..., center=face_mesh_center, pivot=face_mesh_center, all_verts=True)` で縮小
- BODY は box/pivot (box 中央) 基準のまま

### 4. プレビューと mod 出力の分離保証

- export がプレビューの loc を一切使わないことを確認:
  - BODY: `display_to_position_vb(v.co)` (loc=0 なので v.co がそのまま表示位置)
  - 顔: `display_to_game(v.co)` (v.co は draw_vb 空間のまま、loc 不使用)
- 顔メッシュの縮小は draw_vb 空間の v.co に対して行う (プレビューの loc と独立)

### 5. テスト

- 最近傍変換: 変位加算の正しさ (合成データで検証)
- pivot = box 中央: origin が center になること
- 顔メッシュ縮小中心: 顔メッシュ bbox 中心基準で縮小されること
- プレビュー配置と export の独立性: loc を変えても export 結果が不変
- 既存テストの更新 (pivot 関連の期待値)

### 6. バージョン

- bl_info → (2, 0, 0)

## 検証手順

1. 全テスト pass (test_preview_adjust / test_units_ui / test_auto_setup_select / test_build_headshrink_mod / test_build_headshrink_units)
2. py_compile OK
3. Blender 実機: auto_setup → 顔メッシュが BODY 頭部に重なる (プレビューで目視) → box 初期配置 → 手動で box 移動 (pivot 追従) → preview_apply → export → ゲーム確認
4. AppData 同期 + git push

## リスク・注意点

- 顔メッシュの近似変換は「見た目」のための近似 (スキニング逆変換ではない)。ポーズが大きく傾いてる場合は配置がずれる → 手動調整で補正
- 顔メッシュの縮小中心 (顔メッシュ自身の中心) と BODY の縮小中心 (box 中央) が異なるため、CopyDispatch の固定差分と VB 置換の混在で境界に僅かなズレが出る可能性 (ベネット実物も同じ構成で動作実績あり)
