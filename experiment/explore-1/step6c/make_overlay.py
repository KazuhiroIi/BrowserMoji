"""目視確認用オーバーレイ生成 (step6c)。

各手法の予測セル(赤)と細筆GTスケルトン(青)を、元画像(幅800pxに縮小)の上に重ねる。
出力: overlay/{predictor}/{stem}.jpg
"""
import sys
from pathlib import Path

import cv2
import numpy as np

STEP1 = Path(__file__).resolve().parent.parent.parent / "explore-2" / "step1"
WORK_THIN = STEP1 / "work-thin"
sys.path.insert(0, str(STEP1))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "step6"))
import score as base  # noqa: E402
import score_thin  # noqa: E402
import predictors  # noqa: E402

OUT = Path(__file__).resolve().parent / "overlay"
W = 800
IMAGES = ["face2", "high_contrast1", "scene1", "room1"]
PREDS = {
    "baseline": predictors.predict_baseline,
    "canny": predictors.predict_canny,
    "pca": predictors.predict_pca,
    "nms": predictors.predict_nms,
    "b2": predictors.predict_b2,
}

for name in IMAGES:
    thin_path = WORK_THIN / f"{name}.jpg"
    if not thin_path.exists():
        print(f"skip {name}: no thin GT")
        continue
    # 細筆GTスケルトン(フル解像度で抽出し、縮小尺に合わせる)
    img = cv2.imread(str(thin_path))
    b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    red = ((r > 180) & (g < 80) & (b < 80)).astype(np.uint8)
    H, Wf = red.shape
    skel_full = cv2.dilate(
        (score_thin.skeletonize(red.astype(bool)).astype(np.uint8) * 255).astype(np.uint8),
        np.ones((3, 3), np.uint8),
    )
    scale = W / Wf
    skel_small = cv2.resize(skel_full, (W, int(H * scale)), interpolation=cv2.INTER_AREA)

    orig = cv2.imread(str(STEP1 / "work" / "orig" / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE)
    orig_full = cv2.resize(orig, (W, int(orig.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    base_img = cv2.cvtColor(orig_full, cv2.COLOR_GRAY2BGR)
    base_img = cv2.addWeighted(base_img, 0.75, np.full_like(base_img, 255), 0.25, 0)

    fh = skel_small.shape[0]
    # 予測セル → 縮小尺ピクセルへ
    rows, cols = base.cell_grid((H, Wf))
    ch = H / rows
    cw = Wf / cols

    for pname, pfn in PREDS.items():
        o = base.resize_to_feature(orig)
        pred, _ = pfn(o)
        pred = pred[:rows, :cols]
        mask_full = cv2.resize(
            (pred * 255).astype(np.uint8), (Wf, H), interpolation=cv2.INTER_NEAREST
        )
        mask_full = cv2.dilate(mask_full, np.ones((5, 5), np.uint8))
        mask_small = cv2.resize(mask_full, (W, fh), interpolation=cv2.INTER_AREA) > 64

        canvas = base_img.copy()
        canvas[mask_small] = (0, 0, 255)  # 予測: 赤
        gt_m = skel_small > 64
        canvas[gt_m] = (255, 128, 0)  # GT: 青
        out_dir = OUT / pname
        out_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_dir / f"{name}.jpg"), canvas)
        print(f"saved {pname}/{name}.jpg")
