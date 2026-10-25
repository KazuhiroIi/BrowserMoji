"""試作全体で共有する設定（architecture.md §1 の「設定を 1 か所に集約」の試作版）。

調整値はここに集める。CLI から上書きできるものは各スクリプトの引数に露出している。
"""

from __future__ import annotations
import sys

# 出力の文字化け・クラッシュ防止（Windows のコンソールは cp932 のことがある）
def force_utf8_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# アトラス / 表示
ATLAS_COLS = 16          # アトラス PNG の列数
DEFAULT_CELL_PX = 64     # セル（正方形）の 1 辺 px
DEFAULT_FS = 16          # 特徴量計算に使うセル内部の 1 辺 px

# 方式 A
EDGE_THRESHOLD = 0.14    # 勾配強度のしきい値（セル内最大 |Sobel| 。0..1、単位ステップで 1）
COHERENCE_MIN = 0.25     # 勾配ベクトルの整合性の下限（細い線は向きが定まらないので置換しない）

# 方式 B（重み付き最近傍）
W_DENSITY = 1.0          # 濃度の重み
W_DIR8 = 1.0             # 8 方向線分強度の重み（ブロック内平均）
W_REGION4 = 0.7          # 4×4 領域パターンの重み（ブロック内平均）
LINENESS_MIN = 0.15      # これ未満のセル（線分が検出できない平滑領域）は線文字を候補から外す

# 計測
BENCH_COLS = (48, 80, 120)
BENCH_TRIALS = 7
