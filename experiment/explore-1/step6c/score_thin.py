"""細筆アノテーション用の採点 (step6c)。

explore-2/step1/score.py の太筆GTを前提とした抽出(skeletonize + brush_dilate=3)と
異なり、細筆GTでは:

- 正解セル抽出: 赤マスクをフル解像度で skeletonize し、スケルトン画素が属するセルを
  陽性(1.0)とする。黄色は使用しない。
- precision: 予測セル中心が、赤マスクを brush_dilate セル分(デフォルト1)膨張した
  領域に入るか。太筆のような大きな許容幅は不要。

使い方:
  ..\\..\\explore-2\\.venv\\Scripts\\python.exe score_thin.py --images face2 high_contrast1 scene1

前提: explore-2/step1/work-thin/<name>.jpg に細筆アノテーション画像があること。
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from skimage.morphology import skeletonize

STEP1 = Path(__file__).resolve().parent.parent.parent / "explore-2" / "step1"
WORK_THIN = STEP1 / "work-thin"
sys.path.insert(0, str(STEP1))
import score as base  # noqa: E402  (resize_to_feature / cell_grid / 予測器を流用)


def extract_gt_thin(painted_path: Path, brush_dilate: int = 1):
    """細筆GT: 赤マスクのスケルトン画素が属するセルを陽性とする。"""
    img = cv2.imread(str(painted_path))
    b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    red = ((r > 180) & (g < 80) & (b < 80)).astype(np.uint8)
    H, W = red.shape
    rows, cols = base.cell_grid((H, W))
    skel = skeletonize(red.astype(bool)).astype(np.uint8)
    # スケルトン画素をセル座標にマップ
    ys, xs = np.nonzero(skel)
    lab = np.zeros((rows, cols), np.float32)
    if len(ys):
        ch = H / rows
        cw = W / cols
        rows_idx = np.minimum((ys / ch).astype(int), rows - 1)
        cols_idx = np.minimum((xs / cw).astype(int), cols - 1)
        lab[rows_idx, cols_idx] = 1.0
    # precision 用: 赤マスク自体(細筆なので太くない)を brush_dilate セル分膨張
    ch, cw = H // rows, W // cols
    ann_cell = red[: rows * ch, : cols * cw].reshape(rows, ch, cols, cw).mean(axis=(1, 3))
    ann_cell = (ann_cell > 0.5).astype(np.uint8)
    return lab, ann_cell


def score_image_thin(name, pred_fn, brush_dilate=1, sigma=2.0, beta=0.5):
    """beta: Fβ の β (β<1 で precision 重視、β>1 で recall 重視)。"""
    gt, ann_cell = extract_gt_thin(WORK_THIN / f"{name}.jpg", brush_dilate)
    rows, cols = gt.shape
    orig = cv2.imread(str(STEP1 / "work" / "orig" / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE)
    orig = base.resize_to_feature(orig)
    pred, _ = pred_fn(orig)
    pred = pred[:rows, :cols]

    # F1 (ソフトラベルなし: 単純2値)
    soft = gt.reshape(-1)
    p = pred.reshape(-1).astype(np.float32)
    tp = np.minimum(soft, p).sum()
    prec = tp / max(p.sum(), 1e-9)
    rec = tp / max(soft.sum(), 1e-9)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)

    # skel 基準: GT 自体がスケルトンなので recall はそのまま
    pd = pred.astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    pred_dil = cv2.dilate(pd, kernel).astype(bool)
    skel_rec = (pred_dil[gt.astype(bool)]).mean() if gt.any() else 0.0
    ann_dil = cv2.dilate(ann_cell, np.ones((brush_dilate * 2 + 1,) * 2, np.uint8)).astype(bool)
    skel_prec = pred[ann_dil].mean() if pred.any() else 0.0
    skel_f1 = 2 * skel_prec * skel_rec / max(skel_prec + skel_rec, 1e-9)
    b2_ = beta * beta
    skel_fbeta = (1 + b2_) * skel_prec * skel_rec / max(b2_ * skel_prec + skel_rec, 1e-9)
    f_beta = (1 + b2_) * prec * rec / max(b2_ * prec + rec, 1e-9)

    # dist_decay
    big = cv2.resize((gt * 255).astype(np.uint8), (cols * base.CELL, rows * base.CELL), interpolation=cv2.INTER_NEAREST)
    dist = cv2.distanceTransform((big < 128).astype(np.uint8), cv2.DIST_L2, 3) / base.CELL
    dist_cell = cv2.resize(dist, (cols, rows), interpolation=cv2.INTER_AREA)
    decay = np.exp(-(dist_cell ** 2) / (2 * sigma ** 2))
    aux = decay[pred].mean() if pred.any() else 0.0

    return {
        "image": name,
        "edge_cells_pred": int(pred.sum()),
        "edge_cells_gt": int(gt.sum()),
        "F1_cell": round(float(f1), 4),
        "F_beta": round(float(f_beta), 4),
        "P_cell": round(float(prec), 4),
        "R_cell": round(float(rec), 4),
        "skel_P": round(float(skel_prec), 4),
        "skel_R": round(float(skel_rec), 4),
        "skel_F1": round(float(skel_f1), 4),
        "skel_F_beta": round(float(skel_fbeta), 4),
        "dist_decay": round(float(aux), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*", default=None)
    ap.add_argument("--preds", nargs="*", default=None, help="predictors.py の関数名を絞る場合")
    ap.add_argument("--beta", type=float, default=0.5, help="Fβ の β (デフォルト0.5: precision重視)")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "step6"))
    import predictors  # step6 の予測器を流用

    names_all = [p.stem for p in sorted(WORK_THIN.glob("*.jpg"))]
    names = names_all if not args.images else [n for n in names_all if n in args.images]
    preds_all = {
        "baseline": predictors.predict_baseline,
        "canny": predictors.predict_canny,
        "pca": predictors.predict_pca,
        "nms": predictors.predict_nms,
        "b2": predictors.predict_b2,
    }
    if args.preds:
        preds_all = {k: v for k, v in preds_all.items() if k in args.preds}

    for pname, pfn in preds_all.items():
        results = [score_image_thin(n, pfn, beta=args.beta) for n in names]
        print(f"\n=== {pname} ===")
        keys = ["F1_cell", "F_beta", "P_cell", "R_cell", "skel_P", "skel_R", "skel_F1", "skel_F_beta", "dist_decay"]
        hdr = f"{'image':<18}" + "".join(f"{k:>10}" for k in keys)
        print(hdr)
        for r in results:
            print(f"{r['image']:<18}" + "".join(f"{r[k]:>10.4f}" for k in keys))
        if results:
            print(f"{'MEAN':<18}" + "".join(f"{np.mean([r[k] for r in results]):>10.4f}" for k in keys))


if __name__ == "__main__":
    main()
