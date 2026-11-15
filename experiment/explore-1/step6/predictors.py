# -*- coding: utf-8 -*-
"""step6: セル単位エッジマス分類 予測器群 (score.py 互換インターフェース)。

すべて predict(gray) -> (pred, mag) を返す。
  gray : score.py の score_image が渡す 1600px 幅にリサイズ済みグレースケール画像
  pred : (rows, cols) bool セルグリッド (rows, cols = score.py cell_grid に準拠)
  mag  : セル単位の強度配列 (使用しなくても返す)

手法:
  predict_baseline : score.py の predict_sobel と同等 (Sobel 勾配上位15%)
  predict_canny    : bilateral → Canny(50,150) → セル内エッジ画素比率 > 0.1
  predict_pca      : 同じエッジマップで セル内エッジ画素>=15 & PCA σ2/σ1<0.25
  predict_nms      : セル強度(エッジ画素数) + 半径2局所最大 & 強度下限
  predict_b2       : PCA判定 → 8近傍 主軸差<=45° チェーン(長さ>=3) → 孤立成分除去(<5)
"""
import cv2
import numpy as np

COLS = 100
CELL = 16


def cell_grid(shape):
    """score.py cell_grid と同じ: cols=100 固定, 正方形セル."""
    h, w = shape
    cell = w / COLS
    rows = max(1, int(h / cell))
    return rows, COLS


def cell_reduce(img, reducer):
    """(H, W) 画像を rows x cols セルに集約。はみ出し分は 0 パディング."""
    rows, cols = cell_grid(img.shape)
    h, w = img.shape[:2]
    ch = h // rows
    cw = w // cols
    top, left = rows * ch, cols * cw
    pad = np.zeros((top, left), dtype=img.dtype)
    pad[:h, :w] = img[:top, :left]
    blocks = pad.reshape(rows, ch, cols, cw)
    return reducer(blocks)


def canny_edges(gray):
    """共通前段: bilateral → Canny(50,150) → 0/255 エッジマップ."""
    g = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
    return cv2.Canny(g, 50, 150)


def cell_edge_counts(edge):
    """セル内エッジ画素(>0)数マップ."""
    return cell_reduce((edge > 0).astype(np.float32), lambda b: b.sum(axis=(1, 3)))


# ---------------------------------------------------------------- baseline
def predict_baseline(gray):
    """score.py predict_sobel と同等 (複製)."""
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy) / (4 * 255.0)
    rows, cols = cell_grid(gray.shape)
    cellmag = cell_reduce(mag, lambda b: b.mean(axis=(1, 3)))
    thr = np.quantile(cellmag, 0.85)
    pred = cellmag > thr
    return pred, mag


# ---------------------------------------------------------------- canny
def predict_canny(gray):
    edge = canny_edges(gray)
    cnt = cell_edge_counts(edge)
    ratio = cnt / (CELL * CELL)
    return ratio > 0.1, ratio


# ---------------------------------------------------------------- pca
def _cell_pca(edge):
    """セルごとの (エッジ画素数, σ2/σ1, theta)。条件未達セルは (cnt, NaN, NaN)."""
    ys, xs = np.nonzero(edge > 0)
    rows, cols = cell_grid(edge.shape)
    n = rows * cols
    cnt = np.zeros(n, dtype=np.int32)
    ratio = np.full(n, np.nan)
    theta = np.full(n, np.nan)
    if ys.size:
        pts = np.stack([xs, ys], axis=1).astype(np.float64)
        # 16px 固定セル。はみ出し分は最も近いセルにクランプ (rows, cols = cell_grid)
        cells = (np.minimum(ys // CELL, rows - 1) * cols
                 + np.minimum(xs // CELL, cols - 1))
        order = np.argsort(cells, kind="stable")
        cells_s = cells[order]
        pts_s = pts[order]
        bounds = np.searchsorted(cells_s, np.arange(n + 1))
        for ci in range(n):
            s, e = bounds[ci], bounds[ci + 1]
            if e - s < 15:  # MIN_EDGE_PX
                continue
            p = pts_s[s:e]
            if np.ptp(p[:, 0]) < 1.0 and np.ptp(p[:, 1]) < 1.0:
                continue
            c = p - p.mean(axis=0)
            cov = c.T @ c / len(c)
            evals, evecs = np.linalg.eigh(cov)
            s1 = float(np.sqrt(max(evals[1], 1e-12)))
            s2 = float(np.sqrt(max(evals[0], 1e-12)))
            r = s2 / s1
            cy, cx = divmod(ci, cols)
            cnt[cy * cols + cx] = e - s
            ratio[ci] = r
            v = evecs[:, 1]
            theta[ci] = np.arctan2(v[1], v[0]) % np.pi
    return (cnt.reshape(rows, cols), ratio.reshape(rows, cols), theta.reshape(rows, cols))


def predict_pca(gray):
    edge = canny_edges(gray)
    cnt, ratio, _ = _cell_pca(edge)
    pred = (cnt >= 15) & (ratio < 0.25)
    mag = cnt.astype(np.float32)
    return pred, mag


# ---------------------------------------------------------------- nms
def nms_cells(C, r, min_val):
    """セル強度 C の半径 r 近傍で局所最大 & min_val 以上のセル (bool)."""
    Hc, Wc = C.shape
    pad = np.pad(C, r, mode="constant", constant_values=-1.0)
    local_max = np.full((Hc, Wc), -1.0, dtype=np.float32)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            local_max = np.maximum(local_max, pad[r + dy:r + dy + Hc, r + dx:r + dx + Wc])
    return (C >= local_max - 1e-6) & (C >= min_val)


def predict_nms(gray):
    edge = canny_edges(gray)
    cnt = cell_edge_counts(edge)
    pred = nms_cells(cnt, 2, 5.0)  # 強度下限: セル内エッジ画素 5 個
    return pred, cnt


# ---------------------------------------------------------------- b2 (step5 推奨)
def _angle_diff(a, b):
    d = np.abs(a - b) % np.pi
    return np.minimum(d, np.pi - d)


def _chain(mask, theta, angle_th):
    """8近傍・主軸方向差<=angle_th の接続で連結成分化し、長さ>=3 のチェーンのみ残す."""
    n, m = mask.shape
    label = np.full((n, m), -1, dtype=np.int32)
    sizes = []
    for sy in range(n):
        for sx in range(m):
            if not mask[sy, sx] or label[sy, sx] != -1:
                continue
            cid = len(sizes)
            stack = [(sy, sx)]
            label[sy, sx] = cid
            c = 0
            while stack:
                y, x = stack.pop()
                c += 1
                ty = theta[y, x]
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        yy, xx = y + dy, x + dx
                        if not (0 <= yy < n and 0 <= xx < m):
                            continue
                        if label[yy, xx] != -1 or not mask[yy, xx]:
                            continue
                        if np.isnan(ty) or np.isnan(theta[yy, xx]):
                            continue
                        if _angle_diff(ty, theta[yy, xx]) > angle_th:
                            continue
                        label[yy, xx] = cid
                        stack.append((yy, xx))
            sizes.append(c)
    if not sizes:
        return np.zeros_like(mask)
    sizes_a = np.array(sizes, dtype=np.int32)
    return (label >= 0) & (sizes_a[np.clip(label, 0, None)] >= 3)


def _clean(mask, min_comp=5):
    """8近傍連結成分が <5 セルのものをフィラー化."""
    m = mask.astype(np.uint8)
    n, labels = cv2.connectedComponents(m, connectivity=8)
    out = mask.copy()
    for cid in range(1, n):
        if np.count_nonzero(labels == cid) < min_comp:
            out[labels == cid] = False
    return out


def predict_b2(gray):
    edge = canny_edges(gray)
    cnt, ratio, theta = _cell_pca(edge)
    mask = (cnt >= 15) & (ratio < 0.25)
    chained = _chain(mask, theta, np.deg2rad(45.0))
    pred = _clean(chained)
    return pred, cnt.astype(np.float32)
