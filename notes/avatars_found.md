# Avatar 抽出済みデータ — 2026-08-15

Nilou 専用じゃなくても、抽出成功したアバターは全部メモ。XXMI mod 開発・将来の他キャラ対応・手法確立の参考になる。

## 確認済みアバター

### Tighnari (ティナリ) — `Avatar_Boy_Catalyst_Tighnari`
- **ファイル**: `G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\12189509.blk`
- **抽出元**: AnimeStudio.CLI --export_type Convert (no-filter 動作)
- **mesh 数**: 17/17 (Body LOD chain + Face/Face02 + EyeStar + EffectMesh + EffectHair + Brow LOD chain)
- **head bbox**: Y=0.81–1.59m, X=±0.20m, Z=-0.44/+0.15m → 人間スケール 78cm 頭
- **出力**: `D:\Documents\Default Project\Nilou\anime_nilou_v4\Mesh\` (Body, Body_LOD1/2/3, Face, Face02, Face_Eye, Face_Eye_LOD2/3, Face_LOD2/3, Brow, Brow_LOD2/3, EyeStar, EffectMesh, EffectHair)
- **head shrink 0.65 検証**: ✅ 視覚縮小確認 (render_test_v4\head_baseline.png vs head_shrunk.png)
- **特徴**: プレイアブル。ClassID 43 で普通に読める。Nilou と同じ実装パターンのはず
- **Note**: 12189509.blk に `Avatar_Girl_Sword_Nilou_Model` 3 ヒットあり → Nilou 参照マテリアル含む可能性
- **ユーザー発言**: 「ティナリ。プレイアブルだからニィロウ実装にかなり近い」

### Mitya (ミティア) — `Avatar_Boy_Catalyst_Mitya`
- **ファイル**: `persistent\AssetBundles\blocks\00\00514567.blk` (新キャラ、NPC のみ実装)
- **mesh 数**: 25 (Body LOD chain + Face/Face_Eye + Bang + Pupil + Brow + EffectMesh)
- **head bbox**: Y=0.91–1.71m → 人間スケール 80cm 頭
- **出力**: `D:\Documents\Default Project\Nilou\anime_nilou_v3\Mesh\`
- **head shrink 0.65 検証**: ✅
- **特徴**: NPC なので旧形式 ClassID 43 で読める。プレイアブル未実装
- **Note**: ユーザー判断で mod 対象外

## 候補 .blk (未抽出)

### Nilou (ニィロウ) — `Avatar_Girl_Sword_Nilou`
- **候補 (AssetMap 集計ベース)**: 02050112, 02702837, 00956267, 00495653, 10353076, 08476697, 12189509, 13210138, 14172874, 14754328, 15715429, 01642905, 04523043, 04523851, 05001901, 05689114, 07805173, 09718288, 16076595, 24230448
- **1925 ファイル grep 結果 (2026-08-15)**: mesh 名前含むファイルは 2 個だけ (12189509=Tighnari, 10353076=体型カスタマイズパック)
- **状態**: Nilou mesh 単体を含むファイルは **1925 個の中に存在しない**
- **結論**: 02050112.blk 内にあった `Avatar_Girl_Sword_Nilou_Mat_*` 22 hit はマテリアル、`Avatar_Girl_Sword_Nilou_` 160 hit (08476697) も全部 material/texture 参照
- **本命格納場所**: **MdbComponent (ClassID 1152437153)** → 公開パーサ無し、khang06/genshin-studio 削除済み
- **攻略ルート**:
  1. MDB パーサ自作 (数日〜1週間)

  2. コミュニティフォーク (Eleiyas/AnimeStudio) に MDB 対応追加されるのを待つ

  3. 別キャラ mesh を Nilou mod の代理にする (Tighnari/Mitya ベース)

### その他の確認キャラ (AssetMap 経由で存在確認)
- `Avatar_Boy_Pole_Alyosha_*` (NPC)
- `Avatar_Boy_Pole_Illuga_*` (NPC)
- `Avatar_Boy_Pole_Lohen_*` (NPC)
- `Avatar_Boy_Pole_*` (pole 武器複数)
- `PRIVATE_Jackal_Eye` (NPC)

### 体型カスタマイズパック — 10353076.blk
- **ファイル**: `StreamingAssets\AssetBundles\blocks\00\10353076.blk` (44.7MB)
- **抽出元**: AnimeStudio.CLI --export_type Convert (no-filter)
- **mesh 数**: 49 extracted + 29 skipped
- **中身**:
  - Body004/005/006/009 (Fat/Standard/Strong 体型変種)
  - Face001/002/003/004 (Fat/Standard/Strong + NoEmo 表情)
  - Hair011/015/016/019 (Fat/Standard 髪型)
- **意味**: 汎用キャラ体型カスタマイズパック (3 sizes × 4 face × N hair)。Nilou 固有 mesh ではない
- **Nilou 参照**: 4 hits (`Avatar_Girl_Sword_Nilou_Model_Body/Face/Face_Eye`) → 他キャラへのクロス参照文字列
- **生成**: D:\Documents\Default Project\Nilou\anime_nilou_10353076\Mesh\ (49 OBJs)

## 実装パターン記録

### 抽出成功条件 (Playable キャラ)
1. **.blk 内に標準 Mesh (ClassID 43) で mesh が格納されている**
2. **AnimeStudio.CLI で `Blb3File` 自動判定 + Oodle 復号 (1630 ブロックが type 9 でも OK)**
3. **`--export_type Convert` が type フィルタなしで正常動作** (`--types Mesh` 等のフィルタは Nothing exported になる既知バグ)
4. **OBJs は `mesh/mesh_name` 階層に出力**

### 抽出失敗条件 (要回避)
1. ClassID 1152437153 (MdbComponent) 内の mesh → 公開パーサ無し、khang06/genshin-studio 削除済み
2. AssetMap.index 経由の参照 → 別 .blk 解決必要 → 失敗
3. `--names` / `--types` フィルタ → 「Nothing exported」になる

## ファイルマッピングまとめ

| キャラ | 内部名 | 武器 | .blk | 形式 | メッシュ |
|---|---|---|---|---|---|
| Mitya | Avatar_Boy_Catalyst_Mitya | 触媒 | 00514567 | Blb3File | 25 |
| Tighnari | Avatar_Boy_Catalyst_Tighnari | 触媒 | 12189509 | Blb3File | 17 |
| Nilou | Avatar_Girl_Sword_Nilou | 単手剣 | (未特定) | Blb3File | (mesh未抽出) |

武器 (Catalyst/Sword) による分類:
- 触媒キャラ: Mitya, Tighnari (両方成功)
- 単手剣キャラ: Nilou, Ayaka, Lumine 等
- 法器キャラ: Nilou
- 武器種と抽出可否は無関係 (mesh 格納場所はそもそもファイル単位)

## 次の作業

1. 1925 ファイルから `Avatar_Girl_Sword_Nilou_Model_*` パターン grep
2. ヒットした .blk を AnimeStudio で mesh 抽出
3. 見つからない場合 → Tighnari/Mitya の構造を reverse → Nilou 専用ファイル backtrack
