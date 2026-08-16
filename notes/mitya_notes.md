# Mitya 参考データ (Nilou 検索後の保険)

**取得元:** persistent/AssetBundles/blocks/00/00514567.blk
**AnimeStudio 出力:** D:\Documents\Default Project\Nilou\anime_nilou_v3\

## キャラクタ識別
- 内部名: **Mitya** (Avatar_Boy_Catalyst)
- 性別: 男 (Boy)
- 武器: 触媒 (Catalyst)
- Texture: `Avatar_Boy_Catalyst_Mitya_Tex_Body_Diffuse`, `Avatar_Boy_Catalyst_Mitya_Tex_Body_Lightmap`
- 状態: 2026年最新キャラ。今回のmod対象外 (ユーザー指示)

## メッシュ数
- Mesh: **25** (.obj ファイル)
- Animator: **110**
- MonoBehaviour: 2,282
- AnimationClip: 67
- Texture2D: 3
- Material: (AnimeStudio で出力されず)

## Mesh 名前 (container -1353845892)
Bang, Body, Brow, Face, Face_LOD2, Face_LOD3, Face_Eye, Face_Eye_LOD2, Face_Eye_LOD3,
Body_Eye, Body_LOD1, Body_LOD2, Body_LOD3,
Bang_LOD1, Bang_LOD2, Bang_LOD3,
Brow_LOD2, Brow_LOD3,
Pupil, Pupil_LOD1, Pupil_LOD2, Pupil_LOD3,
EyeStar, EffectMesh

## スケール数値
- 身長: Y = 0–1.71 m
- 幅: X = ±0.47 m
- 奥行き: Z = ±0.36 m (LOD含めて ±0.48)
- 頭部bbox: Y = 0.91–1.71 m

## 分類 (head shrink ロジック)
- head メッシュ (19): Face*, Brow*, Bang*, Pupil*, EyeStar, EffectMesh
- body メッシュ (5): Body, Body_LOD1/2/3, Body_Eye
- 除外: Area_Zd_Build* (風景)

## Container IDs (同一 .blk 内に複数キャラ共存)
- -1353845892 (Mitya 本体)
- 331322569, 1412823167, 1890076595, -1264970577 (他キャラ)
