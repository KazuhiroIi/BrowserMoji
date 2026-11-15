# -*- coding: utf-8 -*-
"""step8: pca-canny ベスト (mep5 / r0.35 / er0.02) に後段ステージを追加して精度改善を検証。

ステージ:
  chain   : 方向一貫性チェーン (8近傍・主軸方向差<=45°、チェーン長>=3 のみ採用)
  clean   : 孤立セル除去 (8近傍連結成分 <5 セルをフィラー化)
  stripe  : 横縞抑制 (タワー中層の横縞テクスチャへの誤爆対策)
            - セル勾配 |gy|/|gx| 比 + 主軸 θ がほぼ水平 の帯セルを検出
            - 8近傍連結した帯成分ごとに、列方向へは太らず横に長いバンドか確認
              (列スパン >= STRIPE_MIN_COLS かつ 行スパン <= STRIPE_MAX_ROWS)
            - 各バンド内で「列ごとに最もエッジ強度が高い1行のみ」残す

variant: base / +clean / +chain / +chain+clean / +stripe / +stripe+clean
採点: step6c score_thin.py 方式 (細筈GT 15枚, MEAN + 画像別)
オーバーレイ: face2 / scene2 / high_contrast1 -> step8/overlay/{variant}/{stem}.jpg

使い方:
  ..\\..\\explore-2\\.venv\\Scripts\\python.exe improve.py [--overlay-only]
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
EXPL = HERE.parent
STEP7 = EXPL / "step7"
STEP6 = EXPL / "step6"
STEP1 = EXPL.parent / "explore-2" / "step1"
sys.path.insert(0, str(STEP7))
sys.path.insert(0, str(STEP6))

import predictors  # noqa: E402  (cell_grid / cell_reduce / canny_edges / _chain / _clean)
from skimage.morphology import skeletonize  # noqa: E402
from sweep import (  # noqa: E402  (step7 と同一の共通処理)
    STEP1 as SW_STEP1, WORK_THIN, cell_grid, metrics_thin, resize_to_feature,
)
# 細筆GT抽出は step6c score_thin.py 方式 (skimage skeletonize) を使う
# (explore-2 venv には cv2.ximgproc がないため sweep.extract_gt_thin は使わない)
sys.path.insert(0, str(EXPL / "step6c"))
from score_thin import extract_gt_thin  # noqa: E402

CELL = 16
COLS = 100

# --- base パラメータ (step7 best: pca-canny/mep5_r0.35_er0.02) ---
MIN_EDGE_PX = 5
RATIO_TH = 0.35
EDGE_RATE = 0.02

# --- ステージパラメータ ---
ANGLE_TH = np.deg2rad(45.0)   # chain: 主軸方向差
CHAIN_MIN = 3                 # chain: チェーン長
MIN_COMP = 5                  # clean: 連結成分の最小セル数
STRIPE_ANISO = 0.60           # stripe: |gy|/(|gy|+|gx|) しきい値 (横エッジほど1に近い)
STRIPE_TH_DEG = 30.0          # stripe: 主軸が水平 (θ≈0) とみなす角度差
STRIPE_MIN_COLS = 8           # stripe: 横長バンド判定 (列スパン)
STRIPE_MAX_ROWS = 4           # stripe: 横長バンド判定 (行スパンの上限)

VARIANTS = ["base", "+clean", "+chain", "+chain+clean", "+stripe", "+stripe+clean"]
OVERLAY_STEMS = ["face2", "scene2", "high_contrast1"]


# ---------------------------------------------------------------- PCA (theta 付き)
def pca_cell_stats_theta(edge):
    """セルごとの (エッジ画素数, σ2/σ1, 主軸θ)。>=3点のセルで計算 (mep5 用)。"""
    ys, xs = np.nonzero(edge > 0)
    rows, cols = cell_grid(edge.shape)
    n = rows * cols
    cnt = np.zeros(n, np.int32)
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
            if e - s < 3:
                continue
            p = pts_s[s:e]
            if np.ptp(p[:, 0]) < 1.0 and np.ptp(p[:, 1]) < 1.0:
                continue
            c = p - p.mean(axis=0)
            cov = c.T @ c / len(c)
            evals, evecs = np.linalg.eigh(cov)
            s1 = float(np.sqrt(max(evals[1], 1e-12)))
            s2 = float(np.sqrt(max(evals[0], 1e-12)))
            cnt[ci] = e - s
            ratio[ci] = s2 / s1
            v = evecs[:, 1]
            theta[ci] = np.arctan2(v[1], v[0]) % np.pi
    return cnt.reshape(rows, cols), ratio.reshape(rows, cols), theta.reshape(rows, cols)


# ---------------------------------------------------------------- 勾配方向のセル集約
def cell_grad_aniso(gray):
    """セルごとの |gy|,|gx| 平均と縦横異方性 |gy|/(|gy|+|gx|) を返す。
    横エッジ (水平線) は gy が支配的で aniso≈1。"""
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    m_gx = predictors.cell_reduce(np.abs(gx), lambda b: b.mean(axis=(1, 3)))
    m_gy = predictors.cell_reduce(np.abs(gy), lambda b: b.mean(axis=(1, 3)))
    with np.errstate(invalid="ignore"):
        aniso = m_gy / np.maximum(m_gy + m_gx, 1e-9)
    return m_gy, m_gx, aniso


def angle_diff(a, b):
    d = np.abs(a - b) % np.pi
    return np.minimum(d, np.pi - d)


# ---------------------------------------------------------------- stripe: 横縞セルの間引き
def stripe_thin(pred, theta, aniso, strength):
    """横縞バンドのセルを間引く。
    1) pred セルのうち |gy| 比 > STRIPE_ANISO かつ主軸がほぼ水平 のものを「帯セル」に
    2) 帯セルを8近傍連結 → 横長な成分 (列スパン >= STRIPE_MIN_COLS) を「縞テクスチャ」候補に
    3) 成分内の列ごとに、縦に連なる帯セルのランを見て
       「最もエッジ強度が高い1行のみ」残す
    """
    horiz = np.zeros_like(pred)
    ok = ~np.isnan(theta)
    horiz[ok] = angle_diff(theta[ok], 0.0) <= np.deg2rad(STRIPE_TH_DEG)
    stripe = pred & (aniso > STRIPE_ANISO) & horiz
    if not stripe.any():
        return pred, {"stripe_cells": 0, "thinned": 0}

    n, lbl = cv2.connectedComponents(stripe.astype(np.uint8), connectivity=8)
    out = pred.copy()
    thinned = 0
    for cid in range(1, n):
        comp = lbl == cid
        ys, xs = np.nonzero(comp)
        col_span = xs.max() - xs.min() + 1
        if col_span < STRIPE_MIN_COLS:
            continue
        # 列ごとに縦ラン (連続する帯セル) を切り、各ランで最強の1行のみ残す
        for x in np.unique(xs):
            rows_c = np.sort(ys[xs == x])
            runs = np.split(rows_c, np.nonzero(np.diff(rows_c) > 2)[0] + 1)
            for run in runs:
                if len(run) < 2:
                    continue
                best = run[np.argmax(strength[run, x])]
                for r in run:
                    if r != best:
                        out[r, x] = False
                        thinned += 1
    info = {"stripe_cells": int(stripe.sum()), "thinned": int(thinned)}
    return out, info


# ---------------------------------------------------------------- variant 構成
def apply_variant(base_pred, theta, aniso, strength, variant):
    info = {}
    chain_used = "+chain" in variant
    clean_used = variant.endswith("+clean")
    stripe_used = "+stripe" in variant

    pred = base_pred
    if chain_used:
        pred = predictors._chain(pred, theta, ANGLE_TH)
        pred = pred & base_pred  # chain は base の部分集合に制限
        info["chain"] = int(pred.sum())
    if stripe_used:
        pred, s_info = stripe_thin(pred, theta, aniso, strength)
        info.update(s_info)
    if clean_used:
        before = int(pred.sum())
        pred = predictors._clean(pred, MIN_COMP)
        info["clean_removed"] = before - int(pred.sum())
    return pred, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlay-only", action="store_true")
    args = ap.parse_args()

    names = [p.stem for p in sorted(WORK_THIN.glob("*.jpg"))]
    data = {}
    for name in names:
        gt, ann_cell = extract_gt_thin(WORK_THIN / f"{name}.jpg")
        rows, cols = gt.shape
        orig = cv2.imread(str(SW_STEP1 / "work" / "orig" / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE)
        gray = resize_to_feature(orig)
        edge = predictors.canny_edges(gray)
        cnt, ratio, theta = pca_cell_stats_theta(edge)
        m_gy, m_gx, aniso = cell_grad_aniso(gray)
        with np.errstate(invalid="ignore"):
            base = (cnt >= MIN_EDGE_PX) & (ratio < RATIO_TH) & (cnt / (CELL * CELL) >= EDGE_RATE)
        data[name] = dict(gt=gt, ann=ann_cell, rows=rows, cols=cols, gray=gray,
                          base=base, theta=theta, aniso=aniso, strength=cnt.astype(np.float32))

    results = {}
    if not args.overlay_only:
        for variant in VARIANTS:
            rows_res = []
            for name in names:
                d = data[name]
                pred, _info = apply_variant(d["base"], d["theta"], d["aniso"],
                                            d["strength"], variant)
                m = metrics_thin(d["gt"], d["ann"], pred)
                m["image"] = name
                m["edge_cells_pred"] = int(pred[:d["rows"], :d["cols"]].sum())
                rows_res.append(m)
            mean = {k: float(np.mean([r[k] for r in rows_res]))
                    for k in ("F1_cell", "P_cell", "R_cell", "skel_P", "skel_R",
                              "skel_F1", "dist_decay")}
            results[variant] = {"mean": mean, "per_image": rows_res}
            print(f"{variant:14s}: skel_F1={mean['skel_F1']:.4f} skel_R={mean['skel_R']:.4f} "
                  f"skel_P={mean['skel_P']:.4f} P_cell={mean['P_cell']:.4f} "
                  f"F1_cell={mean['F1_cell']:.4f} dist={mean['dist_decay']:.4f} "
                  f"cells={sum(r['edge_cells_pred'] for r in rows_res)}")
        (HERE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
        print("saved results.json")

    # --- オーバーレイ ---
    W = 800
    for name in OVERLAY_STEMS:
        if name not in data:
            print(f"skip {name}")
            continue
        d = data[name]
        thin_path = WORK_THIN / f"{name}.jpg"
        img = cv2.imread(str(thin_path))
        b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
        red = ((r > 180) & (g < 80) & (b < 80)).astype(np.uint8)
        H, Wf = red.shape
        skel_full = cv2.dilate(skeletonize(red.astype(bool)).astype(np.uint8) * 255,
                               np.ones((3, 3), np.uint8))
        scale = W / Wf
        skel_small = cv2.resize(skel_full, (W, int(H * scale)), interpolation=cv2.INTER_AREA)
        orig = cv2.imread(str(SW_STEP1 / "work" / "orig" / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE)
        orig_full = cv2.resize(orig, (W, int(orig.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        base_img = cv2.cvtColor(orig_full, cv2.COLOR_GRAY2BGR)
        base_img = cv2.addWeighted(base_img, 0.75, np.full_like(base_img, 255), 0.25, 0)
        fh = skel_small.shape[0]
        gt_m = skel_small > 64

        for variant in VARIANTS:
            pred, _ = apply_variant(d["base"], d["theta"], d["aniso"],
                                    d["strength"], variant)
            pred = pred[:d["rows"], :d["cols"]]
            mask_full = cv2.resize((pred * 255).astype(np.uint8), (Wf, H),
                                   interpolation=cv2.INTER_NEAREST)
            mask_full = cv2.dilate(mask_full, np.ones((5, 5), np.uint8))
            mask_small = cv2.resize(mask_full, (W, fh), interpolation=cv2.INTER_AREA) > 64
            canvas = base_img.copy()
            canvas[mask_small] = (0, 0, 255)   # 予測: 赤
            canvas[gt_m] = (255, 128, 0)       # GT: 青
            out = HERE / "overlay" / variant
            out.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out / f"{name}.jpg"), canvas)
        print(f"overlay saved: {name}")
    print("done")


if __name__ == "__main__":
    main()
