"""エッジマス/フィラーマス分類の採点スクリプト (explore-2 step1)。

入力: work/<name>.jpg (赤=エッジ必須, 黄=どちらでもいい, 無地=フィラー のアノテーション付き画像)
      work/orig/<name>.jpg (元画像。予測器への入力に使う)

グリッドは本番アプリに合わせる: columns=100, featurePx=16
  → 画像を幅 100*16=1600px にリサイズし、16x16px を 1 セルとして扱う。

各セルの正解ラベル:
  セル内で赤の割合が最大なら 1.0 (エッジ必須)
  黄の割合が最大なら 0.5 (どちらでもいい)
  無地なら 0.0 (フィラー) — ネガティブとして数える

指標 (複数併記):
  1. F1 (セル多数決): yellow を 0.5 重みのソフトラベルとして precision/recall/F1
  2. Skeleton F1: 赤マスクを細線化した「真のエッジ線」基準
     - recall: スケルトンセルのうち、予測エッジが自分 or 8近傍にある割合
     - precision: 予測エッジセルのうち、赤∪黄マスクを brush_dilate セル分膨張した領域に入る割合
  3. 距離減衰 (補助): 予測セル中心と赤マスクの距離 d に対する exp(-d^2/2σ^2) の平均
     (σ はセル単位)。チューニング時の滑らかなフィードバック用。

予測器は --pred で差し替え可能。デフォルトは Sobel 勾配 magnitude の閾値ベースライン。

使い方:
  python score.py                 # 全画像をスコア
  python score.py --images face2  # 特定画像だけ
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from skimage.morphology import skeletonize

WORK = Path(__file__).resolve().parent / "work"
COLS = 100
FEATURE_PX = 16
CELL = FEATURE_PX  # リサイズ後の 1 セル = 16px


def cell_grid(shape):
    """本番 grid.ts と同じ: cols=100 固定, 正方形セル, rows はアスペクト比から自動。"""
    h, w = shape
    cell = w / COLS
    rows = max(1, int(h / cell))
    return rows, COLS


def resize_to_feature(img):
    h, w = img.shape[:2]
    tw = COLS * FEATURE_PX
    th = int(round(h * tw / w))
    return cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)


def extract_gt(painted_path):
    """アノテーション付き画像からセル単位のソフトラベル (0/0.5/1) を作る。"""
    img = cv2.imread(str(painted_path))
    b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    red = ((r > 180) & (g < 80) & (b < 80)).astype(np.float32)
    yel = ((r > 180) & (g > 180) & (b < 100)).astype(np.float32)
    H, W = red.shape
    rows, cols = cell_grid((H, W))
    ch, cw = H // rows, W // cols
    lab = np.zeros((rows, cols), np.float32)
    for i in range(rows):
        for j in range(cols):
            sl = (slice(i * ch, (i + 1) * ch), slice(j * cw, (j + 1) * cw))
            fr, fy = red[sl].mean(), yel[sl].mean()
            # 赤を優先 (赤と黄が混在したセルは赤扱い)
            if fr >= 0.5:
                lab[i, j] = 1.0
            elif fy >= 0.5:
                lab[i, j] = 0.5
    return lab


def predict_sobel(gray):
    """ベースライン予測器: Sobel 勾配 magnitude が閾値以上のセルをエッジとする。"""
    g = resize_to_feature(gray)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy) / (4 * 255.0)  # 0..1 程度に正規化
    rows, cols = cell_grid(g.shape)
    ch, cw = g.shape[0] // rows, g.shape[1] // cols
    cellmag = mag[: rows * ch, : cols * cw].reshape(rows, ch, cols, cw).mean(axis=(1, 3))
    thr = np.quantile(cellmag, 0.85)  # 上位15%のセルをエッジとする適応閾値
    pred = cellmag > thr
    return pred, mag


def score_image(name, pred_fn, brush_dilate=3, sigma=2.0):
    gt = extract_gt(WORK / f"{name}.jpg")
    rows, cols = gt.shape
    orig = cv2.imread(str(WORK / "orig" / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE)
    orig = resize_to_feature(orig)
    pred, _ = pred_fn(orig)
    pred = pred[:rows, :cols]

    # --- 指標1: セル多数決 F1 (yellow 0.5) ---
    soft = gt.reshape(-1)
    p = pred.reshape(-1).astype(np.float32)
    tp = np.minimum(soft, p).sum()
    prec = tp / max(p.sum(), 1e-9)
    rec = tp / max(soft.sum(), 1e-9)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)

    # --- 指標2: スケルトン基準 ---
    red_cell = (gt >= 1.0).astype(np.uint8)
    skel = skeletonize(red_cell.astype(bool))
    # recall: スケルトンセルの 8近傍に予測があるか
    pd = pred.astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    pred_dil = cv2.dilate(pd, kernel).astype(bool)
    skel_rec = (pred_dil[skel]).mean() if skel.any() else 0.0
    # precision: 予測セルが 赤∪黄 の膨張領域に入るか
    ann_cell = (gt > 0).astype(np.uint8)
    ann_dil = cv2.dilate(ann_cell, np.ones((brush_dilate * 2 + 1, brush_dilate * 2 + 1), np.uint8)).astype(bool)
    skel_prec = pred[ann_dil].mean() if pred.any() else 0.0
    skel_f1 = 2 * skel_prec * skel_rec / max(skel_prec + skel_rec, 1e-9)

    # --- 指標3: 距離減衰 (補助) ---
    big = cv2.resize((gt * 255).astype(np.uint8), (cols * CELL, rows * CELL), interpolation=cv2.INTER_NEAREST)
    dist = cv2.distanceTransform((big < 128).astype(np.uint8), cv2.DIST_L2, 3) / CELL  # セル単位の距離
    dist_cell = cv2.resize(dist, (cols, rows), interpolation=cv2.INTER_AREA)
    decay = np.exp(-(dist_cell ** 2) / (2 * sigma ** 2))
    aux = decay[pred].mean() if pred.any() else 0.0

    return {
        "image": name,
        "edge_cells_pred": int(pred.sum()),
        "edge_cells_gt": int((gt >= 1.0).sum()),
        "F1_cell": round(float(f1), 4),
        "P_cell": round(float(prec), 4),
        "R_cell": round(float(rec), 4),
        "skel_P": round(float(skel_prec), 4),
        "skel_R": round(float(skel_rec), 4),
        "skel_F1": round(float(skel_f1), 4),
        "dist_decay": round(float(aux), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*", default=None)
    args = ap.parse_args()

    names = [p.stem for p in sorted(WORK.glob("*.jpg"))]
    if args.images:
        names = [n for n in names if n in args.images]
    names = [n for n in names if (WORK / "orig" / f"{n}.jpg").exists()]

    results = [score_image(n, predict_sobel) for n in names]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    keys = ["F1_cell", "P_cell", "R_cell", "skel_P", "skel_R", "skel_F1", "dist_decay"]
    hdr = f"{'image':<18}" + "".join(f"{k:>10}" for k in keys)
    print("\n" + hdr)
    for r in results:
        print(f"{r['image']:<18}" + "".join(f"{r[k]:>10.4f}" for k in keys))
    if results:
        print(f"{'MEAN':<18}" + "".join(f"{np.mean([r[k] for r in results]):>10.4f}" for k in keys))


if __name__ == "__main__":
    main()
