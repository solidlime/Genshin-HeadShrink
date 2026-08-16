# PLAN - やりたいこと

## 直近の要望（引き継ぎ書から）
- 全キャラ対応の Blender アドオン（MESH_GROUPS 外出し）
- 3DMigoto .vb/.ib への変換パイプライン
- ゲーム内で mod 動作確認

## 背景メモ（原神 modding）
- miHoYo は配布 mesh の type tree を剥がしている（MD5 のみ）→ Unity bone weights 取得不可
- Nilou の mesh は MdbComponent (ClassID 1152437153) で wraps されていて AnimeStudio では抜ける
- head shrink はアニメ非対応（bone-aware じゃない）→ 静止画向けの実用
- XXMI-Launcher は DisableIB/TextureOverride.ini 形式の mod を読む
