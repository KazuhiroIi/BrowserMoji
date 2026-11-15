# -*- coding: utf-8 -*-
"""step7: 3系統 (pca-canny / nms-canny / edl-bilat) の細筆GTパラメータスイープ。

- 細筆GT: explore-2/step1/work-thin 15枚 (step6c score_thin.py と同じ抽出)
- 各系統: 画像ごとの前計算 (Cannyエッジ / EdgeDrawingセグメント) を1回だけ行い、
  パラメータ違いの判定は軽量なフィルタで実施
- 出力: step7/results.json (全設定スコア) + オーバーレイ (best 設定)

使い方:
  ..\\.venv-b\\Scripts\\python.exe sweep.py [--overlay-only]
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
EXPL = HERE.parent
STEP6C = EXPL / "step6c"
STEP6 = EXPL / "step6"
STEP1 = EXPL.parent / "explore-2" / "step1"
sys.path.insert(0, str(STEP6))

import predictors  # noqa: E402  (cell_grid / cell_edge_counts / nms_cells を利用)

# 注意: この venv (.venv-b) には skimage が無いため explore-2/step1/score.py も
# import できない。cell_grid / resize_to_feature は同一実装をここに置く
# (score.py: cols=100 固定・幅 1600px へ INTER_AREA リサイズ)。
COLS = 100


def cell_grid(shape):
    h, w = shape
    cell = w / COLS
    return max(1, int(h / cell)), COLS


def resize_to_feature(img):
    h, w = img.shape[:2]
    tw = COLS * 16
    th = int(round(h * tw / w))
    return cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)


WORK_THIN = STEP1 / "work-thin"
CELL = 16


# ---------------------------------------------------------------- 細筆GT抽出
def extract_gt_thin(painted_path: Path, brush_dilate: int = 1):
    """細筆GT: 赤マスクのスケルトン画素が属するセルを陽性とする。
    score_thin.extract_gt_thin の thinning を cv2.ximgproc.thinning に置き換えた版。"""
    img = cv2.imread(str(painted_path))
    b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    red = ((r > 180) & (g < 80) & (b < 80)).astype(np.uint8)
    H, W = red.shape
    rows, cols = cell_grid((H, W))
    skel = cv2.ximgproc.thinning(red * 255)
    ys, xs = np.nonzero(skel)
    lab = np.zeros((rows, cols), np.float32)
    if len(ys):
        ch = H / rows
        cw = W / cols
        rows_idx = np.minimum((ys / ch).astype(int), rows - 1)
        cols_idx = np.minimum((xs / cw).astype(int), cols - 1)
        lab[rows_idx, cols_idx] = 1.0
    ch, cw = H // rows, W // cols
    ann_cell = red[: rows * ch, : cols * cw].reshape(rows, ch, cols, cw).mean(axis=(1, 3))
    ann_cell = (ann_cell > 0.5).astype(np.uint8)
    return lab, ann_cell


# ---------------------------------------------------------------- 共通: 細筆指標
def metrics_thin(gt, ann_cell, pred, brush_dilate=1, sigma=2.0):
    """score_thin.score_image_thin の指標計算部分 (予測を事前計算する版)."""
    rows, cols = gt.shape
    pred = pred[:rows, :cols]
    soft = gt.reshape(-1)
    p = pred.reshape(-1).astype(np.float32)
    tp = np.minimum(soft, p).sum()
    prec = tp / max(p.sum(), 1e-9)
    rec = tp / max(soft.sum(), 1e-9)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)

    pd = pred.astype(np.uint8)
    pred_dil = cv2.dilate(pd, np.ones((3, 3), np.uint8)).astype(bool)
    skel_rec = (pred_dil[gt.astype(bool)]).mean() if gt.any() else 0.0
    ann_dil = cv2.dilate(ann_cell, np.ones((brush_dilate * 2 + 1,) * 2, np.uint8)).astype(bool)
    skel_prec = pred[ann_dil].mean() if pred.any() else 0.0
    skel_f1 = 2 * skel_prec * skel_rec / max(skel_prec + skel_rec, 1e-9)

    big = cv2.resize((gt * 255).astype(np.uint8), (cols * CELL, rows * CELL),
                     interpolation=cv2.INTER_NEAREST)
    dist = cv2.distanceTransform((big < 128).astype(np.uint8), cv2.DIST_L2, 3) / CELL
    dist_cell = cv2.resize(dist, (cols, rows), interpolation=cv2.INTER_AREA)
    decay = np.exp(-(dist_cell ** 2) / (2 * sigma ** 2))
    aux = decay[pred].mean() if pred.any() else 0.0

    return {
        "F1_cell": float(f1), "P_cell": float(prec), "R_cell": float(rec),
        "skel_P": float(skel_prec), "skel_R": float(skel_rec), "skel_F1": float(skel_f1),
        "dist_decay": float(aux),
    }


# ---------------------------------------------------------------- pca-canny
def pca_cell_stats(edge):
    """セルごとの (エッジ画素数, σ2/σ1)。MIN_EDGE_PX は後段フィルタで適用するため
    点数>=3 のセルはすべて PCA を計算しておく。"""
    ys, xs = np.nonzero(edge > 0)
    rows, cols = cell_grid(edge.shape)
    n = rows * cols
    cnt = np.zeros(n, np.int32)
    ratio = np.full(n, np.nan)
    if ys.size:
        cells = (np.minimum(ys // CELL, rows - 1) * cols
                 + np.minimum(xs // CELL, cols - 1))
        order = np.argsort(cells, kind="stable")
        cells_s = cells[order]
        bounds = np.searchsorted(cells_s, np.arange(n + 1))
        for ci in range(n):
            s, e = bounds[ci], bounds[ci + 1]
            if e - s < 3:
                continue
            p = np.stack([xs[order[s:e]], ys[order[s:e]]], axis=1).astype(np.float64)
            if np.ptp(p[:, 0]) < 1.0 and np.ptp(p[:, 1]) < 1.0:
                continue
            c = p - p.mean(axis=0)
            evals = np.linalg.eigvalsh(c.T @ c / len(c))
            s1 = np.sqrt(max(evals[1], 1e-12))
            s2 = np.sqrt(max(evals[0], 1e-12))
            cnt[ci] = e - s
            ratio[ci] = s2 / s1
    return cnt.reshape(rows, cols), ratio.reshape(rows, cols)


def pca_pred(stats, min_edge_px, ratio_th, edge_rate):
    cnt, ratio = stats
    with np.errstate(invalid="ignore"):
        return (cnt >= min_edge_px) & (ratio < ratio_th) & (cnt / (CELL * CELL) >= edge_rate)


# ---------------------------------------------------------------- edl-bilat
def _straight_ratio(pts):
    """perp_var / par_var (真っ直ぐさ)。小さいほど直線的。"""
    if len(pts) < 3:
        return 0.0
    c = pts - pts.mean(axis=0)
    cov = c.T @ c / len(c)
    vals = np.linalg.eigvalsh(cov)
    par_var, perp_var = vals[1], vals[0]
    if par_var <= 0:
        return 0.0 if perp_var <= 0 else np.inf
    return perp_var / par_var


def edl_segments(gray, grad_th):
    """bilateral 前段 → EdgeDrawing → セグメント [(pts, straight_ratio), ...]"""
    src = cv2.bilateralFilter(gray, d=7, sigmaColor=30, sigmaSpace=7)
    ed = cv2.ximgproc.createEdgeDrawing()
    params = ed.Params()
    params.GradientThresholdValue = grad_th
    params.AnchorThresholdValue = 8
    ed.setParams(params)
    ed.detectEdges(src)
    out = []
    for s in ed.getSegments():
        pts = np.asarray(s, dtype=np.float64)  # (x, y)
        out.append((pts, _straight_ratio(pts)))
    return out


def edl_pred(segments, rows, cols, ratio_th, min_seg_points):
    """セグメントをセルグリッドにラスタライズ (step3 の polylines 方式)."""
    grid = np.zeros((rows, cols), np.uint8)
    pts_list = [np.rint(pts / CELL).astype(np.int32)
                for pts, r in segments if r <= ratio_th and len(pts) >= min_seg_points]
    if pts_list:
        cv2.polylines(grid, pts_list, isClosed=False, color=255, thickness=1, lineType=cv2.LINE_8)
    return grid.astype(bool)


# ---------------------------------------------------------------- 本体
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlay-only", action="store_true")
    ap.add_argument("--overlay-cfg", default=None, help="追加でオーバーレイを生成する設定名 (step3忠実な edl-bilat/g32_r0.5_msp15 など)")
    args = ap.parse_args()

    names = [p.stem for p in sorted(WORK_THIN.glob("*.jpg"))]
    data = {}
    for name in names:
        gt, ann_cell = extract_gt_thin(WORK_THIN / f"{name}.jpg")
        rows, cols = gt.shape
        orig = cv2.imread(str(STEP1 / "work" / "orig" / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE)
        gray = resize_to_feature(orig)
        edge = predictors.canny_edges(gray)
        pca_stats = pca_cell_stats(edge)
        cnt_nms = predictors.cell_edge_counts(edge)
        segs32 = edl_segments(gray, 32)
        segs20 = edl_segments(gray, 20)
        data[name] = dict(gt=gt, ann=ann_cell, rows=rows, cols=cols,
                          pca=pca_stats, cnt=cnt_nms, segs={32: segs32, 20: segs20})

    # --- 設定一覧 ---
    configs = []  # (system, cfg_name, pred_fn(data) -> pred grid)
    for mep in (5, 10):
        for rth in (0.25, 0.30, 0.35):
            for er in (0.02, 0.05):
                cfg = dict(min_edge_px=mep, ratio_th=rth, edge_rate=er)
                configs.append((
                    "pca-canny",
                    f"pca-canny/mep{mep}_r{rth:.2f}_er{er}",
                    lambda d, c=cfg: pca_pred(d["pca"], c["min_edge_px"], c["ratio_th"], c["edge_rate"]),
                ))
    for r in (1, 2):
        for mv in (2, 5, 10):
            cfg = dict(r=r, min_val=mv)
            configs.append((
                "nms-canny",
                f"nms-canny/r{r}_mv{mv}",
                lambda d, c=cfg: predictors.nms_cells(d["cnt"], c["r"], float(c["min_val"])),
            ))
    for grad in (32, 20):
        for rth in (0.5, 1.0):
            for msp in (5, 15):
                cfg = dict(grad=grad, ratio_th=rth, min_seg=msp)
                configs.append((
                    "edl-bilat",
                    f"edl-bilat/g{grad}_r{rth:.1f}_msp{msp}",
                    lambda d, c=cfg: edl_pred(d["segs"][c["grad"]], d["rows"], d["cols"],
                                              c["ratio_th"], c["min_seg"]),
                ))
    print(f"config count: {len(configs)} (pca-canny 12, nms-canny 6, edl-bilat 8)")

    results = {}
    if not args.overlay_only:
        for sys_name, cfg_name, fn in configs:
            rows_res = []
            for name in names:
                d = data[name]
                pred = fn(d)
                m = metrics_thin(d["gt"], d["ann"], pred)
                m["image"] = name
                m["edge_cells_pred"] = int(pred[:d["rows"], :d["cols"]].sum())
                rows_res.append(m)
            mean = {k: float(np.mean([r[k] for r in rows_res]))
                    for k in ("F1_cell", "P_cell", "R_cell", "skel_P", "skel_R", "skel_F1", "dist_decay")}
            results[cfg_name] = {"system": sys_name, "mean": mean, "per_image": rows_res}
            print(f"{cfg_name}: skel_F1={mean['skel_F1']:.4f} skel_R={mean['skel_R']:.4f} "
                  f"skel_P={mean['skel_P']:.4f} P_cell={mean['P_cell']:.4f} "
                  f"F1_cell={mean['F1_cell']:.4f} dist={mean['dist_decay']:.4f}")
        (HERE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
        print("saved results.json")

    # --- best 設定 (skel_F1 MEAN 基準) を系統ごとに選択 (results が無ければ best.json から) ---
    best = {}
    for sys_name in ("pca-canny", "nms-canny", "edl-bilat"):
        cand = sorted(((v["mean"]["skel_F1"], k) for k, v in results.items() if v["system"] == sys_name),
                      reverse=True)
        if cand:
            best[sys_name] = cand[0][1]
            print(f"best {sys_name}: {cand[0][1]} skel_F1={cand[0][0]:.4f}")
    if not best:
        best = json.loads((HERE / "best.json").read_text(encoding="utf-8"))
        print(f"loaded best from best.json: {best}")

    # --- オーバーレイ ---
    overlay_stems = ["face2", "high_contrast1", "scene1", "room1", "scene2"]
    W = 800
    for name in overlay_stems:
        if name not in data:
            print(f"skip {name}")
            continue
        d = data[name]
        thin_path = WORK_THIN / f"{name}.jpg"
        img = cv2.imread(str(thin_path))
        b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
        red = ((r > 180) & (g < 80) & (b < 80)).astype(np.uint8)
        H, Wf = red.shape
        skel_full = cv2.dilate(cv2.ximgproc.thinning(red * 255), np.ones((3, 3), np.uint8))
        scale = W / Wf
        skel_small = cv2.resize(skel_full, (W, int(H * scale)), interpolation=cv2.INTER_AREA)
        orig = cv2.imread(str(STEP1 / "work" / "orig" / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE)
        orig_full = cv2.resize(orig, (W, int(orig.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        base_img = cv2.cvtColor(orig_full, cv2.COLOR_GRAY2BGR)
        base_img = cv2.addWeighted(base_img, 0.75, np.full_like(base_img, 255), 0.25, 0)
        fh = skel_small.shape[0]
        gt_m = skel_small > 64

        preds = {}
        overlay_cfgs = dict(best)
        if args.overlay_cfg:
            overlay_cfgs["extra"] = args.overlay_cfg
        for sys_name, cfg_name in overlay_cfgs.items():
            fn = next(f for s, k, f in configs if k == cfg_name)
            pred = fn(d)[:d["rows"], :d["cols"]]
            preds[sys_name] = pred
            mask_full = cv2.resize((pred * 255).astype(np.uint8), (Wf, H), interpolation=cv2.INTER_NEAREST)
            mask_full = cv2.dilate(mask_full, np.ones((5, 5), np.uint8))
            mask_small = cv2.resize(mask_full, (W, fh), interpolation=cv2.INTER_AREA) > 64
            canvas = base_img.copy()
            canvas[mask_small] = (0, 0, 255)  # 予測: 赤
            canvas[gt_m] = (255, 128, 0)      # GT: 青
            out = HERE / "overlay" / sys_name
            out.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out / f"{name}.jpg"), canvas)

        # 比較オーバーレイ: pca-canny=赤 / nms-canny=緑 / edl-bilat=青, GT=黒
        canvas = base_img.copy()
        colors = {"pca-canny": (0, 0, 255), "nms-canny": (0, 255, 0), "edl-bilat": (255, 0, 0)}
        for sys_name, col in colors.items():
            if sys_name not in preds:
                continue
            pred = preds[sys_name]
            mask_full = cv2.resize((pred * 255).astype(np.uint8), (Wf, H), interpolation=cv2.INTER_NEAREST)
            mask_full = cv2.dilate(mask_full, np.ones((5, 5), np.uint8))
            mask_small = cv2.resize(mask_full, (W, fh), interpolation=cv2.INTER_AREA) > 64
            canvas[mask_small] = col
        canvas[gt_m] = (0, 0, 0)
        out = HERE / "overlay" / "compare"
        out.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out / f"{name}.jpg"), canvas)
        print(f"overlay saved: {name}")
    print("done")


if __name__ == "__main__":
    main()
