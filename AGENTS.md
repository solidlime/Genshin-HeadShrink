# Project guide line

## 1. プロジェクト概要
- 本プロジェクトのプラン作成、および回答は全て日本語で行います。
- 原神 (Genshin Impact) のプレイアブルキャラ 3D モデルを抽出し、Blender で部位別拡縮 → XXMI-Launcher (3DMigoto) .ib/.vb mod 化するツール群。
- メイン成果物: Blender アドオン `scripts/headshrink_addon.py`、.blk 解析パイプライン、3DMigoto 変換スクリプト。
- 詳細仕様は `.spec/SPEC.md`、進行中タスクは `.spec/TODO.md` を参照。

## 2. プロジェクト識別
- project: headshrink

# Nous 記憶運用（.agent/ は使わない）

## セッション開始時（必須）
セッション開始時、ユーザーへの最初の応答の前に session-start スキルを実行し、nous 記憶から状態を復元する:
- `get_context` でペルソナ状態・直近サマリを取得
- `## プロジェクト識別` 節から `project: headshrink` タグを取得
- `memory_search(query="headshrink 進行中 OR 全キャラ対応 OR 3DMigoto", top_k=5)` 等で作業状態を復元
- 直近の `session_summary` を取得して続きから開始

## メモリ管理
- 重要情報・決定・作業完了は nous に記録。`project:headshrink` タグ必須
- 状態変化時は `update_context` → `memory_create` の順で永続化
- `.agent/memory/MEMORY.md` / `.agent/handoff/HANDOFF.md` は使用しない（nous 記憶が代替）
- ローカルの自動メモリ機能（~/.claude/ 配下）は使用しない

## ハンドオフ管理
- セッション終了時の session_summary 生成（終了フック）が引継を代替する
- 手動引継が必要な場合は `memory_create(tags=["project:headshrink", "session_summary"])` で記録
- 旧 `引き継ぎ書.md` 形式は補助として残してよいが、公式引継は nous 記憶

## 仕様駆動開発（SDD）ルール
- コーディングや業務作業を開始する前に、必ず `.spec/` 配下の4ファイルを確認・更新すること
- 作業の順序：PLAN（目的確認）→ SPEC（要件確認）→ TODO（タスク確認）→ 実作業
- **PLAN.mdは人間の口頭メモ・自由記述**であり、箇条書き・口語・断片的な内容で構わない
- PLAN.mdを読んだら、そのまま実装に入らず、不明点をヒアリングしながらSPEC.mdを作成・確定させること
- SPEC.mdが確定してからTODO.mdのタスク分解を行い、ユーザーの承認を得てから実作業を開始する
- 作業完了後は TODO.md の該当タスクにチェックを入れ、KNOWLEDGE.md に学びを記録する
- 仕様が不明確な場合は作業を開始せず、ユーザーに確認してから SPEC.md を更新する

## サブエージェント運用
- 探索・調査: #009 (explorer)
- 実装・修正: #011 (fixer)
- ドキュメント調査: #042 (librarian)
- UI/UX: #057 (designer)
- アーキテクチャ判断・コードレビュー: #081 (oracle)
- 機械的・単一ファイル20行未満は直接実行可
