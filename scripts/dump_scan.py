"""dump_scan.py — 同一キャラの複数 FrameAnalysis を跨いで extra_hash 候補を検出。

1フレームだけ別hashに差し替わるキャラ (例: Noelle の MOUTH d265427c) は、
同一 vert_count の別 vb0 hash としてダンプに現れる。このスクリプトは
キャラのダンプ親ディレクトリ (FrameAnalysis-* を複数含む) を走査し、
vb0 hash を vert_count でグループ化して「同サイズの別hash」を extra_hash
候補として提示する。

Usage:
    python dump_scan.py <char_dump_dir> [--stride 40]

例:
    python dump_scan.py assets/Dump/Barbara

出力: 各 vert_count グループについて、複数 hash がある場合に
    vert_count=32800  hashes=7a1146c2, 91407707, f36e1afa
のように表示する。1つ目の hash が通常、残りが extra_hash 候補。

# ponytail: 過度な自動化はしない。候補の提示のみで、face_offsets.json への
# 書き込みは行わない (ユーザーが確認して手動追記する)。将来、同一
# vert_count の別hashを自動で extra_hashes に反映したい場合は、ここで
# 返した groups を face_offsets.json の __config__.extra_hashes に
# マージする関数を追加すればよい (拡張ポイント)。
"""
import argparse
import os
import re
from collections import defaultdict

_VB0_RE = re.compile(r'^\d+-vb0=([0-9a-fA-F]{8})')


def scan_vb0_hashes(dump_dir, stride=40):
    """複数 FrameAnalysis を跨いで vb0 hash を vert_count でグループ化。

    Returns: {vert_count: {hash8: [file_path...]}} — 全サブディレクトリ
    (FrameAnalysis-*) を再帰走査し、vb0 .buf ファイルのサイズから
    vert_count を導出する。同一 hash は複数フレーム/フォルダで重複する
    ため set で集約する。
    """
    groups = defaultdict(lambda: defaultdict(set))
    for root, _dirs, files in os.walk(dump_dir):
        for fn in files:
            m = _VB0_RE.match(fn)
            if not m or not fn.lower().endswith('.buf'):
                continue
            h = m.group(1).lower()
            path = os.path.join(root, fn)
            vert_count = os.path.getsize(path) // stride
            groups[vert_count][h].add(path)
    return groups


def extra_hash_candidates(groups):
    """同一 vert_count に複数 hash があるグループを候補として返す。

    Returns: [(vert_count, [hash8...])] — hash は出現順 (通常hashが先頭)。
    """
    out = []
    for vc in sorted(groups):
        hashes = sorted(groups[vc])
        if len(hashes) > 1:
            out.append((vc, hashes))
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Scan a char dump dir (multiple FrameAnalysis) for "
                    "same-vert_count different-hash vb0 candidates.")
    ap.add_argument("dump_dir", help="Character dump parent dir (contains FrameAnalysis-*)")
    ap.add_argument("--stride", type=int, default=40, help="VB stride in bytes (default 40)")
    args = ap.parse_args()

    groups = scan_vb0_hashes(args.dump_dir, args.stride)
    candidates = extra_hash_candidates(groups)
    print(f"vb0 groups: {len(groups)} distinct vert_count, "
          f"{sum(len(h) for h in groups.values())} distinct hashes")
    if not candidates:
        print("No same-vert_count different-hash candidates found.")
        return
    print("\n=== extra_hash candidates (same vert_count, different hash) ===")
    for vc, hashes in candidates:
        print(f"  vert_count={vc:<6} hashes={', '.join(hashes)}")
    print("\n# 通常hashが先頭、残りが extra_hash 候補。face_offsets.json の")
    print("# 該当キャラ __config__.extra_hashes に手動追記する。例:")
    print('#   "extra_hashes": {"MOUTH": ["<hash8>"]}')


if __name__ == "__main__":
    main()
