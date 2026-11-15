"""Step4 案A: 共通後処理レイヤー — step3 の3候補に同一の後処理を適用。

パイプライン:
  1. 孤立エッジセル除去: 白セル(>200)の8近傍連結成分、サイズ<5セルはフィラー化
     (フィラー値 = 元画像セル平均輝度を再計算して塗る)
  2. ギャップ埋め: 白セルマスクに 3x3 closing (1回)
  3. セルスケルトン化: skimage.morphology.skeletonize で太い塊を1セル幅に細線化

variant:
  clean       = 1
  clean-close = 1 + 2
  full        = 1 + 2 + 3

出力:
  step4/postprocess/out/{pca-canny|nms-canny|edl-bilat}/{clean|clean-close|full}/{stem}.jpg
  step4/postprocess/montage/{stem}.jpg   (original + baseline3 + full3 = 7タイル、4列グリッド)
"""

from pathlib import Path

import cv2
import numpy as np
from skimage.morphology import binary_closing, binary_dilation, skeletonize, square

ROOT = Path(__file__).resolve().parent
EXPL = ROOT.parent.parent
DATA_DIR = EXPL.parent.parent / "data"

CANDIDATES = {
    "pca-canny": EXPL / "step3" / "pca-shape" / "out" / "canny-low50",
    "nms-canny": EXPL / "step3" / "cell-nms" / "out" / "canny-low50",
    "edl-bilat": EXPL / "step3" / "edlines-cells" / "out" / "edp-bilateral",
}

OUT_DIR = ROOT / "out"
MONTAGE_DIR = ROOT / "montage"

MAX_SIDE = 1280
CELL = 16
WHITE_TH = 200
MIN_COMPONENT = 5  # これ未満の連結成分はフィラー化
VARIANTS = ["clean", "clean-close", "full"]


def load_gray(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read: {path}")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def cellify(shape: tuple[int, int]) -> tuple[int, int]:
    """セルグリッドの (行数, 列数)。端の余りセルは捨てる(step3 実装に合わせる)。"""
    h, w = shape
    return h // CELL, w // CELL


def to_cell_mask(vis: np.ndarray, n_rows: int, n_cols: int) -> np.ndarray:
    """可視化画像から「白セルマスク」をセル単位で復元。白比率>0.95 のセルを白とみなす。"""
    mask = np.zeros((n_rows, n_cols), dtype=bool)
    for r in range(n_rows):
        for c in range(n_cols):
            cell = vis[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL]
            mask[r, c] = (cell > WHITE_TH).mean() > 0.95
    return mask


def remove_isolated(mask: np.ndarray) -> np.ndarray:
    """8近傍連結成分のサイズ < MIN_COMPONENT の白セルを落とす。"""
    from scipy import ndimage

    lbl, n = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
    if n == 0:
        return mask.copy()
    sizes = np.bincount(lbl.ravel())
    keep = sizes >= MIN_COMPONENT
    keep[0] = False
    return keep[lbl]


def close_gaps(mask: np.ndarray) -> np.ndarray:
    return binary_closing(mask, footprint=np.ones((3, 3), dtype=bool))


def thin_skeleton(mask: np.ndarray) -> np.ndarray:
    return skeletonize(mask).astype(bool)


def render(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """白セル=255、それ以外=元画像セル平均輝度でセル単位に塗る。"""
    n_rows, n_cols = mask.shape
    h, w = gray.shape
    canvas = np.zeros((h, w), dtype=np.uint8)
    for r in range(n_rows):
        for c in range(n_cols):
            y0, x0 = r * CELL, c * CELL
            if mask[r, c]:
                canvas[y0:y0 + CELL, x0:x0 + CELL] = 255
            else:
                canvas[y0:y0 + CELL, x0:x0 + CELL] = gray[y0:y0 + CELL, x0:x0 + CELL].mean()
    return canvas


def main() -> None:
    paths = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".png"})
    n_out = 0
    for p in paths:
        stem = p.stem
        gray = load_gray(p)
        n_rows, n_cols = cellify(gray.shape)

        # candidate -> variant -> 可視化画像
        tiles_full: dict[str, np.ndarray] = {}
        for cand_name, cand_dir in CANDIDATES.items():
            vis_in = cv2.imread(str(cand_dir / f"{stem}.jpg"), cv2.IMREAD_GRAYSCALE)
            if vis_in is None:
                raise RuntimeError(f"failed to read baseline: {cand_dir / (stem + '.jpg')}")
            if vis_in.shape != gray.shape:
                vis_in = cv2.resize(vis_in, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)

            mask0 = to_cell_mask(vis_in, n_rows, n_cols)
            mask1 = remove_isolated(mask0)
            mask2 = close_gaps(mask1)
            mask3 = thin_skeleton(mask2)

            renders = {
                "clean": render(gray, mask1),
                "clean-close": render(gray, mask2),
                "full": render(gray, mask3),
            }
            for var, vis in renders.items():
                outp = OUT_DIR / cand_name / var
                outp.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(outp / f"{stem}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 90])
                n_out += 1
            tiles_full[cand_name] = renders["full"]

        # montage: original + 3 baselines + 3 full = 7 tiles, 4 columns
        tiles = [cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)]
        labels = ["original"]
        for cand_name, cand_dir in CANDIDATES.items():
            base = cv2.imread(str(cand_dir / f"{stem}.jpg"), cv2.IMREAD_GRAYSCALE)
            if base.shape != gray.shape:
                base = cv2.resize(base, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
            tiles.append(cv2.cvtColor(base, cv2.COLOR_GRAY2BGR))
            labels.append(f"{cand_name} base")
        for cand_name in CANDIDATES:
            tiles.append(cv2.cvtColor(tiles_full[cand_name], cv2.COLOR_GRAY2BGR))
            labels.append(f"{cand_name} full")

        tile_h, tile_w = tiles[0].shape[:2]
        label_h = 28
        cols = 4
        rows = (len(tiles) + cols - 1) // cols
        montage = np.zeros((label_h + rows * (tile_h + 4) - 4, (tile_w + 4) * cols - 4, 3), dtype=np.uint8)
        for i, (t, lab) in enumerate(zip(tiles, labels)):
            rr, cc = divmod(i, cols)
            y = label_h + rr * (tile_h + 4)
            x = cc * (tile_w + 4)
            montage[y:y + tile_h, x:x + tile_w] = t
            cv2.putText(montage, lab, (x + 4, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        MONTAGE_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(MONTAGE_DIR / f"{stem}.jpg"), montage, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"done: {n_out} processed images, {len(paths)} montages")


if __name__ == "__main__":
    main()
