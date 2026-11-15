"""Step3 案2: pca-shape — セル内エッジ画素(>128)が15個以上なら PCA。

σ2/σ1 (直交方向/主軸方向の標準偏差比) < 0.25 → 細長い=線 → エッジマス。
エッジ画素が少ないセルはフィラー。

出力:
  step3/pca-shape/out/{canny-low50|edp|xdog}/{stem}.jpg
  step3/pca-shape/montage/{stem}.jpg
"""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
EXPL = ROOT.parent.parent
DATA_DIR = EXPL.parent.parent / "data"
EDGE_DIRS = {
    "canny-low50": EXPL / "step2" / "canny-improved" / "out" / "bilateral-low50-clean",
    "edp": EXPL / "step2" / "edge-drawing" / "out" / "edp-default",
    "xdog": EXPL / "step2" / "xdog" / "out" / "xdog-standard",
}
OUT_DIR = ROOT / "out"
MONTAGE_DIR = ROOT / "montage"

MAX_SIDE = 1280
CELL = 16
MIN_EDGE_PX = 15
LINE_RATIO_TH = 0.25


def load_gray(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read: {path}")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def is_line(cell_e: np.ndarray) -> bool:
    ys, xs = np.nonzero(cell_e > 128)
    if ys.size < MIN_EDGE_PX:
        return False
    pts = np.stack([xs, ys], axis=1).astype(np.float64)
    pts -= pts.mean(axis=0)
    cov = pts.T @ pts / pts.shape[0]
    evals = np.linalg.eigvalsh(cov)  # ascending
    sigma1 = float(np.sqrt(max(evals[1], 1e-12)))
    sigma2 = float(np.sqrt(max(evals[0], 1e-12)))
    return (sigma2 / sigma1) < LINE_RATIO_TH


def render(gray: np.ndarray, edge: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    canvas = np.zeros((h, w), dtype=np.uint8)
    for cy in range(0, h - CELL + 1, CELL):
        for cx in range(0, w - CELL + 1, CELL):
            if is_line(edge[cy:cy + CELL, cx:cx + CELL]):
                canvas[cy:cy + CELL, cx:cx + CELL] = 255
            else:
                canvas[cy:cy + CELL, cx:cx + CELL] = gray[cy:cy + CELL, cx:cx + CELL].mean()
    return canvas


def main() -> None:
    paths = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".png"})
    n_out = 0
    for p in paths:
        stem = p.stem
        gray = load_gray(p)
        h, w = gray.shape
        tiles = [cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)]
        labels = ["original"]
        for name, d in EDGE_DIRS.items():
            ep = d / (stem + ".jpg")
            if not ep.exists():
                ep = d / p.name
            edge = cv2.imread(str(ep), cv2.IMREAD_GRAYSCALE)
            if edge is None:
                raise RuntimeError(f"failed to read edge: {ep}")
            if edge.shape != (h, w):
                edge = cv2.resize(edge, (w, h), interpolation=cv2.INTER_NEAREST)
            vis = render(gray, edge)
            outp = OUT_DIR / name
            outp.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(outp / f"{stem}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 90])
            n_out += 1
            tiles.append(cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR))
            labels.append(name)

        tile_h, tile_w = tiles[0].shape[:2]
        label_h = 28
        montage = np.zeros((tile_h + label_h, (tile_w + 4) * len(tiles), 3), dtype=np.uint8)
        for i, (t, lab) in enumerate(zip(tiles, labels)):
            x = i * (tile_w + 4)
            montage[label_h:label_h + tile_h, x:x + tile_w] = t
            cv2.putText(montage, lab, (x + 4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        MONTAGE_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(MONTAGE_DIR / f"{stem}.jpg"), montage, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"done: {n_out} rendered images, {len(paths)} montages")


if __name__ == "__main__":
    main()
