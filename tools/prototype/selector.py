"""文字選択方式 A / B の基準実装（architecture.md §3）。

方式 A: セルの平均輝度で濃度記号を選ぶ。勾配がしきい値以上のセルは、
        Sobel 勾配の向きに最も近い線記号へ置き換える（太さは勾配強度で段階選び）。
        勾配の向きがセル内で打ち消し合っている（細い線など）場合は置換しない。
方式 B: セル特徴量（濃度・8 方向強度・4×4 パターン）と文字特徴量の
        重み付き最近傍で、文字セット全体から選ぶ。

セル特徴ベクトルの並び（2 トラック契約①）:
  [density(1), dir8(8), region4(16)] = 25 次元
距離: D² = w_d·(Δdensity)² + w_s·mean(Δdir8²) + w_p·mean(Δregion4²)

 NOTE: dir8（DoL 線分強度）は「細い線」には強く反応するが、
 単調なグラデーション（エッジの面）には 0 に近い値を返す
 （フランク減算が一次の変化を打ち消すため）。エッジの向きは
 方式 A では Sobel 勾配から、方式 B では region4 パターンから拾う。
"""

from __future__ import annotations

import numpy as np

import charset
import config
import glyphfeat

N_FEAT = 1 + glyphfeat.N_DIR + glyphfeat.REGION * glyphfeat.REGION


def char_matrix(records: list[dict]) -> np.ndarray:
    """features.json の chars → (C, 25) float32 行列。"""
    m = np.empty((len(records), N_FEAT), dtype=np.float32)
    for i, r in enumerate(records):
        m[i, 0] = r["density"]
        m[i, 1:1 + glyphfeat.N_DIR] = r["dir8"]
        m[i, 1 + glyphfeat.N_DIR:] = r["region4"]
    return m


def _nn_distance(cell_block: np.ndarray, char_block: np.ndarray, weight: float) -> np.ndarray:
    """ブロックごとの重み付き二乗距離: (M, d) vs (C, d) → (M, C)。||a||²+||b||²−2ab を使う。"""
    ca2 = (cell_block * cell_block).sum(axis=1, keepdims=True)        # (M, 1)
    cb2 = (char_block * char_block).sum(axis=1)                       # (C,)
    dot = cell_block @ char_block.T                                   # (M, C)
    return weight * np.maximum(ca2 + cb2[None, :] - 2.0 * dot, 0.0)


def _orientation_from_dir8(dir8: np.ndarray) -> np.ndarray:
    """dir8 (..., 8) → 線の向き [0, π)。2 倍角の円周平均で mod π をまたぐ。"""
    th = np.deg2rad(np.asarray(glyphfeat.DIRECTIONS_DEG, dtype=np.float32))
    c = dir8 * np.cos(2.0 * th)
    s = dir8 * np.sin(2.0 * th)
    return np.mod(np.arctan2(s.sum(-1), c.sum(-1)) / 2.0, np.pi)


class SelectorBase:
    def __init__(self, records: list[dict]):
        self.records = records
        self.ids = np.array([r["id"] for r in records], dtype=np.int32)
        self.mat = char_matrix(records)
        self.i_d = slice(0, 1)
        self.i_s = slice(1, 1 + glyphfeat.N_DIR)
        self.i_p = slice(1 + glyphfeat.N_DIR, N_FEAT)


class SelectorA(SelectorBase):
    """方式 A: 輝度 → 濃度記号、エッジセルは勾配の向きに合う線記号へ置換。"""

    def __init__(self, records: list[dict], edge_threshold: float = config.EDGE_THRESHOLD,
                 coherence_min: float = config.COHERENCE_MIN):
        super().__init__(records)
        self.edge_threshold = edge_threshold
        self.coherence_min = coherence_min  # 勾配ベクトルの整合性の下限（細い線は置換しない）
        self.density_rows = np.array(
            sorted((k for k, r in enumerate(records) if r["group"] == "density"),
                   key=lambda k: records[k]["density"]), dtype=np.int64
        )
        self.density_values = np.array([records[k]["density"] for k in self.density_rows], dtype=np.float32)
        # 線記号は「まっすぐな線」に限る（角・T 字は向きが一意でない。T-5 の調整に相当）
        straight = [k for k, r in enumerate(records)
                    if r["group"] == "line" and r["char"] in charset.STRAIGHT_LINE_CHARS]
        self.line_rows = np.array(straight or
                                  [k for k, r in enumerate(records) if r["group"] == "line"],
                                  dtype=np.int64)
        self.line_angles = _orientation_from_dir8(self.mat[self.line_rows][:, self.i_s])
        self.line_densities = self.mat[self.line_rows][:, 0]

    def select(self, lum: np.ndarray, gmag: np.ndarray, gvec: np.ndarray,
               gmag_mean: np.ndarray) -> np.ndarray:
        """lum: (rows, cols) 平均輝度（1=白）, gmag: (rows, cols) 勾配強度（セル内 max）,
        gvec: (rows, cols, 2) セル平均勾配ベクトル, gmag_mean: (rows, cols) 勾配強度のセル平均
        → 文字 id の (rows, cols)。

        エッジ検出はセル内最大 |勾配|（細いエッジがセル平均で希釈されるのを避ける）。
        置換の対象は「境界を実際に含むセル」に限る: 整合性 = |平均勾配ベクトル| /
        平均 |勾配| が高いセルだけ（境界の隣のセルは max だけ高いが向きが打ち消し
        合うので除外される）。
        """
        rows, cols = lum.shape
        ink_level = np.clip(1.0 - lum, 0.0, 1.0).ravel()
        # 平坦セル: 濃度記号のうち最も近い濃度のもの
        pos = np.searchsorted(self.density_values, ink_level)
        pos = np.clip(pos, 1, len(self.density_values) - 1)
        lo, hi = pos - 1, pos
        take_lo = np.abs(ink_level - self.density_values[lo]) <= np.abs(ink_level - self.density_values[hi])
        pick = np.where(take_lo, self.density_rows[lo], self.density_rows[hi])
        ids = self.ids[pick].reshape(rows, cols).copy()

        gx, gy = gvec[..., 0], gvec[..., 1]
        coherence = np.hypot(gx, gy) / (gmag_mean + 1e-6)
        use = (gmag >= self.edge_threshold) & (coherence >= self.coherence_min)
        if use.any():
            ang = np.mod(np.arctan2(-gx[use], gy[use]), np.pi)            # 線の向き [0, π)
            d = np.abs(ang[:, None] - self.line_angles[None, :])
            d = np.minimum(d, np.pi - d)                                  # 折り返し
            target = np.clip(gmag[use], 0.0, 1.0)                         # 弱いエッジ → 細い線
            score = (d / (np.pi / 8.0)) ** 2 + 0.5 * (self.line_densities[None, :] - target[:, None]) ** 2
            ids[use] = self.ids[self.line_rows[np.argmin(score, axis=1)]]
        return ids


class SelectorB(SelectorBase):
    """方式 B: 文字セット全体との重み付き最近傍。

    線分がほとんど検出できない平滑セル（dir8 の最大値が LINENESS_MIN 未満）
    では線文字を候補から外す。線文字は濃度が低く dir8 のコストも小さいため、
    除外しないと平滑な中間調に線文字が吸われ、すじ状のノイズになるため。
    """

    def __init__(self, records: list[dict], lineness_min: float = config.LINENESS_MIN):
        super().__init__(records)
        self.lineness_min = lineness_min
        self.line_col_mask = np.array([r["group"] == "line" for r in records], dtype=bool)

    def select(self, density: np.ndarray, dir8: np.ndarray, region4: np.ndarray) -> np.ndarray:
        """density: (rows, cols), dir8: (8, rows, cols), region4: (rows, cols, 4, 4)。"""
        rows, cols = density.shape
        m = rows * cols
        feat = np.zeros((m, N_FEAT), dtype=np.float32)
        feat[:, 0] = density.ravel()
        feat[:, self.i_s] = dir8.reshape(glyphfeat.N_DIR, m).T
        feat[:, self.i_p] = region4.reshape(m, glyphfeat.REGION * glyphfeat.REGION)
        d_d = _nn_distance(feat[:, self.i_d], self.mat[:, self.i_d], config.W_DENSITY)
        d_s = _nn_distance(feat[:, self.i_s], self.mat[:, self.i_s], config.W_DIR8)
        d_p = _nn_distance(feat[:, self.i_p], self.mat[:, self.i_p], config.W_REGION4)
        # 平滑セル（線分が検出できない領域）では dir8 を比較しない。
        # 記号・かななどの「構造のある薄い文字」の dir8 は小さくないため、
        # 比較に入れると平滑な中間調が全部 空白（space）に吸われてしまう。
        smooth = dir8.max(axis=0).ravel() < self.lineness_min
        d_s[smooth, :] = 0.0
        dist = d_d + d_s + d_p
        # 線文字も候補から外す（dir8 を比較しない以上、濃度の低い線文字が
        # 密度だけで選ばれる恐れがあるため）
        dist[smooth[:, None] & self.line_col_mask[None, :]] = np.inf
        return self.ids[np.argmin(dist, axis=1)].reshape(rows, cols)


def load_table(json_path) -> list[dict]:
    import json
    return json.loads(json_path.read_text(encoding="utf-8"))["chars"]
