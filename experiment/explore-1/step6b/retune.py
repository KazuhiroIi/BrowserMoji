# -*- coding: utf-8 -*-
"""step6b: 1600px スケール向け しきい値再調整 + 適応閾値(quantile)モード + oracle 評価.

- 固定しきい値: 各手法のパラメータをグリッド探索し, 画像全体の MEAN を報告
- 適応閾値モード: 各画像について「予測エッジセル数 ≈ 正解エッジセル数」になるよう
  セル強度の上位 K (= gt エッジセル数) を選ぶ (quantile ベース). 最も公平な比較.
- oracle: 各画像ごとに最良のしきい値設定を選んだ場合の skel_F1 (しきい値感度の上限参考値)

使い方:
  python retune.py            # 全評価実行 → results.md 用のデータを出力
"""
import sys
import json
from pathlib import Path

import cv2
import numpy as np
from skimage.morphology import skeletonize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))                      # step6/predictors.py 用
sys.path.insert(0, str(HERE.parent.parent / "explore-2" / "step1"))  # score.py 用

from step6.predictors import (  # noqa: E402
    cell_grid, cell_reduce, canny_edges, cell_edge_counts, nms_cells,
    _angle_diff, _chain, _clean, predict_baseline,
)
from score import WORK, COLS, FEATURE_PX, extract_gt, resize_to_feature  # noqa: E402

CELL = 16


# ---------------------------------------------------------------- 前段 (画像ごと1回)
class ImgCtx:
    """1画像について計算コストの高い前段を1回だけ計算して保持."""

    def __init__(self, name):
        self.name = name
        self.gt = extract_gt(WORK / f"{name}.jpg")
        rows, cols = self.gt.shape
        self.gt_shape = (rows, cols)
        gray = cv2.imread(str(WORK / "orig" / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE)
        self.gray = resize_to_feature(gray)
        self.edge = canny_edges(self.gray)
        self.cnt = cell_edge_counts(self.edge)          # セル内エッジ画素数
        self.ratio = self.cnt / (CELL * CELL)
        self.cnt_full, self.sig_ratio, self.theta = cell_pca(self.edge, min_pts=2)
        # gt 由来の指標用マスク
        red_cell = (self.gt >= 1.0).astype(np.uint8)
        self.skel = skeletonize(red_cell.astype(bool))
        self.ann_cell = (self.gt > 0).astype(np.uint8)
        self.ann_dil = cv2.dilate(self.ann_cell, np.ones((7, 7), np.uint8)).astype(bool)
        # dist_decay 用
        big = cv2.resize((self.gt * 255).astype(np.uint8),
                         (cols * CELL, rows * CELL), interpolation=cv2.INTER_NEAREST)
        dist = cv2.distanceTransform((big < 128).astype(np.uint8), cv2.DIST_L2, 3) / CELL
        self.dist_decay_base = cv2.resize(dist, (cols, rows), interpolation=cv2.INTER_AREA)
        self.gt_cells = int((self.gt >= 1.0).sum())
        # baseline 用 cellmag
        gx = cv2.Sobel(self.gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(self.gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.hypot(gx, gy) / (4 * 255.0)
        self.cellmag = cell_reduce(mag, lambda b: b.mean(axis=(1, 3)))

    def pred_ok(self, pred):
        """pred を gt 形状に合わせる (はみ出し除去 / 不足パディング)."""
        rows, cols = self.gt_shape
        out = np.zeros((rows, cols), bool)
        pr = min(pred.shape[0], rows)
        pc = min(pred.shape[1], cols)
        out[:pr, :pc] = pred[:pr, :pc]
        return out

    def metrics(self, pred_raw):
        """score.py score_image と同じ指標を pred から計算."""
        pred = self.pred_ok(pred_raw)
        soft = self.gt.reshape(-1)
        p = pred.reshape(-1).astype(np.float32)
        tp = np.minimum(soft, p).sum()
        prec = tp / max(p.sum(), 1e-9)
        rec = tp / max(soft.sum(), 1e-9)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)

        pd = pred.astype(np.uint8)
        pred_dil = cv2.dilate(pd, np.ones((3, 3), np.uint8)).astype(bool)
        skel_rec = (pred_dil[self.skel]).mean() if self.skel.any() else 0.0
        skel_prec = pred[self.ann_dil].mean() if pred.any() else 0.0
        skel_f1 = 2 * skel_prec * skel_rec / max(skel_prec + skel_rec, 1e-9)

        decay = np.exp(-(self.dist_decay_base ** 2) / (2 * 2.0 ** 2))
        aux = decay[pred].mean() if pred.any() else 0.0
        return {
            "pred_cells": int(pred.sum()),
            "gt_cells": self.gt_cells,
            "F1_cell": round(float(f1), 4),
            "P_cell": round(float(prec), 4),
            "R_cell": round(float(rec), 4),
            "skel_P": round(float(skel_prec), 4),
            "skel_R": round(float(skel_rec), 4),
            "skel_F1": round(float(skel_f1), 4),
            "dist_decay": round(float(aux), 4),
        }


def cell_pca(edge, min_pts=2):
    """step6 _cell_pca の最小点数をパラメータ化した版 (min_pts 以上のセルのみ PCA)."""
    ys, xs = np.nonzero(edge > 0)
    rows, cols = cell_grid(edge.shape)
    n = rows * cols
    cnt = np.zeros(n, dtype=np.int32)
    ratio = np.full(n, np.nan)
    theta = np.full(n, np.nan)
    if ys.size:
        pts = np.stack([xs, ys], axis=1).astype(np.float64)
        cells = (np.minimum(ys // CELL, rows - 1) * cols
                 + np.minimum(xs // CELL, cols - 1))
        order = np.argsort(cells, kind="stable")
        cells_s = cells[order]
        pts_s = pts[order]
        bounds = np.searchsorted(cells_s, np.arange(n + 1))
        for ci in range(n):
            s, e = bounds[ci], bounds[ci + 1]
            if e - s < min_pts:
                continue
            p = pts_s[s:e]
            if np.ptp(p[:, 0]) < 1.0 and np.ptp(p[:, 1]) < 1.0:
                continue
            c = p - p.mean(axis=0)
            cov = c.T @ c / len(c)
            evals, evecs = np.linalg.eigh(cov)
            s1 = float(np.sqrt(max(evals[1], 1e-12)))
            s2 = float(np.sqrt(max(evals[0], 1e-12)))
            cy, cx = divmod(ci, cols)
            cnt[cy * cols + cx] = e - s
            ratio[ci] = s2 / s1
            v = evecs[:, 1]
            theta[ci] = np.arctan2(v[1], v[0]) % np.pi
    return cnt.reshape(rows, cols), ratio.reshape(rows, cols), theta.reshape(rows, cols)


def top_k(score, k, invalid=-np.inf):
    """score の上位 k セルを True とする bool マップ (invalid のセルは除外)."""
    s = np.where(np.isfinite(score), score, invalid).astype(np.float64).reshape(-1)
    k = max(0, min(k, s.size))
    if k == 0:
        return (s > np.inf).reshape(score.shape)
    idx = np.argpartition(-s, k - 1)[:k]
    out = np.zeros(s.size, bool)
    out[idx] = True
    return out.reshape(score.shape)


# ---------------------------------------------------------------- 各手法の設定評価
def eval_canny(ctx, thr):
    return ctx.metrics(ctx.ratio > thr)


def eval_pca(ctx, min_px, sig):
    pred = (ctx.cnt_full >= min_px) & (ctx.sig_ratio < sig)
    return ctx.metrics(pred)


def eval_nms(ctx, min_val, radius):
    return ctx.metrics(nms_cells(ctx.cnt.astype(np.float32), radius, float(min_val)))


def eval_b2(ctx, min_px, sig=0.25):
    mask = (ctx.cnt_full >= min_px) & (ctx.sig_ratio < sig)
    chained = _chain(mask, ctx.theta, np.deg2rad(45.0))
    return ctx.metrics(_clean(chained))


def eval_baseline(ctx, q):
    thr = np.quantile(ctx.cellmag, q)
    return ctx.metrics(ctx.cellmag > thr)


# ---------------------------------------------------------------- 適応閾値モード
def eval_adaptive_canny(ctx):
    return ctx.metrics(top_k(np.where(np.isfinite(ctx.ratio), ctx.ratio, 0), ctx.gt_cells))


def eval_adaptive_pca(ctx, min_px, sig):
    score = np.where((ctx.cnt_full >= min_px) & (ctx.sig_ratio < sig), ctx.cnt_full, -np.inf)
    return ctx.metrics(top_k(score, ctx.gt_cells))


def eval_adaptive_nms(ctx, radius):
    keep = nms_cells(ctx.cnt.astype(np.float32), radius, 0.0)
    score = np.where(keep, ctx.cnt.astype(np.float64), -np.inf)
    return ctx.metrics(top_k(score, ctx.gt_cells))


def eval_adaptive_b2(ctx, min_px, sig=0.25):
    mask = (ctx.cnt_full >= min_px) & (ctx.sig_ratio < sig)
    chained = _chain(mask, ctx.theta, np.deg2rad(45.0))
    score = np.where(_clean(chained), ctx.cnt_full.astype(np.float64), -np.inf)
    return ctx.metrics(top_k(score, ctx.gt_cells))


def eval_adaptive_baseline(ctx):
    return ctx.metrics(top_k(ctx.cellmag, ctx.gt_cells))


# ---------------------------------------------------------------- main
def main():
    names = [p.stem for p in sorted(WORK.glob("*.jpg"))
             if (WORK / "orig" / f"{p.stem}.jpg").exists()]
    print(f"images: {len(names)}: {names}", flush=True)

    ctxs = [ImgCtx(n) for n in names]

    configs = []  # (method, label, eval_fn)
    configs.append(("baseline", "q0.80", lambda c: eval_baseline(c, 0.80)))
    configs.append(("baseline", "q0.85(既定)", lambda c: eval_baseline(c, 0.85)))
    configs.append(("baseline", "q0.90", lambda c: eval_baseline(c, 0.90)))
    for thr in (0.04, 0.06, 0.1):
        configs.append(("canny", f"ratio>{thr}", lambda c, t=thr: eval_canny(c, t)))
    for min_px in (5, 6, 8, 10):
        for sig in (0.25, 0.30):
            configs.append(("pca", f"px>={min_px},s2/s1<{sig}",
                            lambda c, m=min_px, s=sig: eval_pca(c, m, s)))
    for min_val in (3, 5, 8):
        for r in (2, 3):
            configs.append(("nms", f"min>={min_val},r={r}",
                            lambda c, v=min_val, rr=r: eval_nms(c, v, rr)))
    for min_px in (5, 6, 8, 10):
        configs.append(("b2", f"px>={min_px},s2/s1<0.25",
                        lambda c, m=min_px: eval_b2(c, m)))
    # 適応閾値モード
    configs.append(("adaptive", "baseline top-K", eval_adaptive_baseline))
    configs.append(("adaptive", "canny top-K(ratio)", eval_adaptive_canny))
    for min_px in (5, 8):
        for sig in (0.25, 0.30):
            configs.append(("adaptive", f"pca top-K(px>={min_px},sig<{sig})",
                            lambda c, m=min_px, s=sig: eval_adaptive_pca(c, m, s)))
    for r in (2, 3):
        configs.append(("adaptive", f"nms top-K(r={r})",
                        lambda c, rr=r: eval_adaptive_nms(c, rr)))
    for min_px in (5, 8):
        configs.append(("adaptive", f"b2 top-K(px>={min_px})",
                        lambda c, m=min_px: eval_adaptive_b2(c, m)))

    keys = ["F1_cell", "P_cell", "R_cell", "skel_P", "skel_R", "skel_F1", "dist_decay"]
    all_rows = []       # (method, label, mean_dict, per_image_oracle_skelF1 list)
    per_image = {}      # (method, label) -> {image: metrics}

    for method, label, fn in configs:
        rows = {}
        try:
            for c in ctxs:
                rows[c.name] = fn(c)
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {method}/{label}: {e}")
            continue
        mean = {k: round(float(np.mean([rows[c.name][k] for c in ctxs])), 4) for k in keys}
        per_image[(method, label)] = rows
        all_rows.append((method, label, mean))
        print(f"done {method}/{label}: skel_F1 MEAN={mean['skel_F1']}", flush=True)

    # oracle: 画像ごとに同一手法内で最良 skel_F1 の設定を選ぶ
    oracle = {}
    for method in ("baseline", "canny", "pca", "nms", "b2", "adaptive"):
        best_sum, best_detail = 0.0, {}
        for c in ctxs:
            best_v, best_lbl = -1.0, None
            for m, label, _ in all_rows:
                if m != method:
                    continue
                v = per_image[(m, label)][c.name]["skel_F1"]
                if v > best_v:
                    best_v, best_lbl = v, label
            best_detail[c.name] = {"label": best_lbl, "skel_F1": best_v}
            best_sum += best_v
        oracle[method] = {"mean_skel_F1": round(best_sum / len(ctxs), 4), "detail": best_detail}

    out = {"images": names, "mean": [
        {"method": m, "label": l, **mv} for m, l, mv in all_rows],
        "oracle": oracle,
        "per_image": {f"{m}|{l}": v for (m, l), v in per_image.items()},
    }
    out_path = HERE / "retune_results.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
