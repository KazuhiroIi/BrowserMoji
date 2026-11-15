"""step1 + step2 で試した全手法を1枚のモンタージュにまとめる.

出力: step2/montage-all/*.jpg (original + 14 variants を 4x4 で並べる)
"""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
STEP1 = ROOT.parent / "step1"
STEP2 = ROOT
DATA_DIR = ROOT.parent.parent.parent / "data"
CELL = 400
PANEL = 26

VARIANTS = [
    ("sobel", STEP1 / "sobel/out"),
    ("laplacian", STEP1 / "laplacian/out"),
    ("canny", STEP1 / "canny/out"),
    ("sob+eq", STEP1 / "sobel-with-equalization/out"),
    ("sob+clahe", STEP1 / "sobel-with-clahe/out"),
    ("sob+gamma", STEP1 / "sobel-with-gamma/out"),
    ("canny-imp-auto", STEP2 / "canny-improved/out/bilateral-auto"),
    ("canny-imp-auto-cl", STEP2 / "canny-improved/out/bilateral-auto-clean"),
    ("canny-imp-low50", STEP2 / "canny-improved/out/bilateral-low50-clean"),
    ("edp-default", STEP2 / "edge-drawing/out/edp-default"),
    ("edp-nfilt", STEP2 / "edge-drawing/out/edp-noise-filtered"),
    ("xdog-soft", STEP2 / "xdog/out/xdog-soft"),
    ("xdog-std", STEP2 / "xdog/out/xdog-standard"),
    ("dog-binary", STEP2 / "xdog/out/dog-binary"),
]
COLS = 4


def load_cell(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read: {path}")
    h, w = img.shape[:2]
    scale = CELL / max(h, w)
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def labeled(cell: np.ndarray, text: str) -> np.ndarray:
    band = np.full((PANEL, cell.shape[1], 3), 30, dtype=np.uint8)
    cv2.putText(band, text, (6, PANEL - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    return np.vstack([band, cell])


def main() -> None:
    out_dir = ROOT / "montage-all"
    out_dir.mkdir(exist_ok=True)
    paths = sorted(
        p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".png"}
    )
    for p in paths:
        cells = [labeled(load_cell(p), "original")]
        for label, d in VARIANTS:
            cells.append(labeled(load_cell(d / f"{p.stem}.jpg"), label))
        rows = (len(cells) + COLS - 1) // COLS
        row_imgs = []
        for r in range(rows):
            row = cells[r * COLS:(r + 1) * COLS]
            wmax = max(c.shape[1] for c in row)
            padded = [
                np.pad(c, ((0, 0), (0, wmax - c.shape[1]), (0, 0)), constant_values=0)
                for c in row
            ]
            hmax = max(c.shape[0] for c in padded)
            padded = [
                np.pad(c, ((0, hmax - c.shape[0]), (0, 0), (0, 0)), constant_values=0)
                for c in padded
            ]
            row_imgs.append(np.hstack(padded))
        wmax = max(r.shape[1] for r in row_imgs)
        row_imgs = [
            np.pad(r, ((0, 0), (0, wmax - r.shape[1]), (0, 0)), constant_values=0)
            for r in row_imgs
        ]
        cv2.imwrite(str(out_dir / f"{p.stem}.jpg"), np.vstack(row_imgs), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"done: {len(paths)} montages -> {out_dir}")


if __name__ == "__main__":
    main()
