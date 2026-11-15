"""各入力画像について、元画像 + 6種類のエッジ検出結果を並べたモンタージュを作成する.

出力: step1/montage/*.jpg
"""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent.parent.parent / "data"
CELL = 480  # 各セルの長辺
PANEL = 28   # ラベル帯の高さ

VARIANTS = [
    ("original", None),
    ("sobel", "sobel"),
    ("laplacian", "laplacian"),
    ("canny", "canny"),
    ("sobel+eq", "sobel-with-equalization"),
    ("sobel+clahe", "sobel-with-clahe"),
    ("sobel+gamma", "sobel-with-gamma"),
]


def load_cell(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read: {path}")
    h, w = img.shape[:2]
    scale = CELL / max(h, w)
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def labeled(cell: np.ndarray, text: str) -> np.ndarray:
    band = np.full((PANEL, cell.shape[1], 3), 30, dtype=np.uint8)
    cv2.putText(band, text, (6, PANEL - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return np.vstack([band, cell])


def main() -> None:
    out_dir = ROOT / "montage"
    out_dir.mkdir(exist_ok=True)
    paths = sorted(
        p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".png"}
    )
    for p in paths:
        cells = []
        for label, sub in VARIANTS:
            src = p if sub is None else ROOT / sub / "out" / f"{p.stem}.jpg"
            cells.append(labeled(load_cell(src), label))
        cols = 4
        rows = (len(cells) + cols - 1) // cols
        grid: list[list[np.ndarray]] = [[] for _ in range(rows)]
        for i, cell in enumerate(cells):
            grid[i // cols].append(cell)
        # 各行を横に並べる(セル幅が異なる場合は右を黒で埋める)
        row_imgs = []
        for row in grid:
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
        montage = np.vstack(row_imgs)
        cv2.imwrite(str(out_dir / f"{p.stem}.jpg"), montage, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"done: {len(paths)} montages -> {out_dir}")


if __name__ == "__main__":
    main()
