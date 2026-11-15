"""Step 1: data/ の全画像にエッジ検出フィルタを適用して出力する.

出力構成:
  step1/{sobel,laplacian,canny}/out/*.jpg            - 前処理なし
  step1/sobel-with-{equalization,clahe,gamma}/out/*.jpg - 前処理あり
"""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent.parent.parent / "data"
MAX_SIDE = 1280

# (folder, filter, preprocessing)
JOBS = [
    ("sobel", "sobel", None),
    ("laplacian", "laplacian", None),
    ("canny", "canny", None),
    ("sobel-with-equalization", "sobel", "equalization"),
    ("sobel-with-clahe", "sobel", "clahe"),
    ("sobel-with-gamma", "sobel", "gamma"),
]


def load_gray(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read: {path}")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def preprocess(gray: np.ndarray, kind: str) -> np.ndarray:
    if kind == "equalization":
        return cv2.equalizeHist(gray)
    if kind == "clahe":
        return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    if kind == "gamma":
        inv_gamma = 1.0 / 0.6
        table = np.array(
            [(i / 255.0) ** inv_gamma * 255 for i in range(256)], dtype=np.uint8
        )
        return cv2.LUT(gray, table)
    return gray


def apply_filter(gray: np.ndarray, kind: str) -> np.ndarray:
    if kind == "sobel":
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        return np.clip(mag, 0, 255).astype(np.uint8)
    if kind == "laplacian":
        lap = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
        mag = np.abs(lap)
        return np.clip(mag, 0, 255).astype(np.uint8)
    if kind == "canny":
        return cv2.Canny(gray, 100, 200)
    raise ValueError(kind)


def main() -> None:
    paths = sorted(
        p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".png"}
    )
    print(f"input: {len(paths)} images")
    for folder, filt, prep in JOBS:
        out_dir = ROOT / folder / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        for p in paths:
            gray = load_gray(p)
            if prep:
                gray = preprocess(gray, prep)
            edge = apply_filter(gray, filt)
            cv2.imwrite(str(out_dir / f"{p.stem}.jpg"), edge, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"done: {folder} ({len(paths)} files)")


if __name__ == "__main__":
    main()
