"""Step 2: Canny 改良版 - bilateralFilter + 自動閾値 + 孤立点除去.

出力構成:
  step2/canny-improved/out/bilateral-auto/*.jpg         - 自動閾値 Canny のみ
  step2/canny-improved/out/bilateral-auto-clean/*.jpg   - + 孤立点・短セグメント除去
  step2/canny-improved/out/bilateral-low50-clean/*.jpg  - low 固定値 50 + 除去
"""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent.parent.parent.parent / "data"
MAX_SIDE = 1280
MIN_AREA = 20

VARIANTS = ["bilateral-auto", "bilateral-auto-clean", "bilateral-low50-clean"]


def load_gray(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read: {path}")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def auto_canny(gray: np.ndarray, low: int | None = None) -> np.ndarray:
    """median に基づく自動閾値 Canny(low を指定すれば固定値)."""
    if low is None:
        v = np.median(gray)
        lo = int(max(0, v * 0.66))
        hi = int(min(255, v * 1.33))
    else:
        lo = low
        hi = low * 3
    return cv2.Canny(gray, lo, hi)


def remove_small_components(edge: np.ndarray, min_area: int = MIN_AREA) -> np.ndarray:
    """面積 min_area 未満の連結成分を削除."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(edge, connectivity=8)
    out = np.zeros_like(edge)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            out[labels == i] = 255
    return out


def main() -> None:
    paths = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".png"})
    print(f"input: {len(paths)} images")
    for p in paths:
        gray = load_gray(p)
        smooth = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
        edges = {
            "bilateral-auto": auto_canny(smooth),
            "bilateral-auto-clean": remove_small_components(auto_canny(smooth)),
            "bilateral-low50-clean": remove_small_components(auto_canny(smooth, low=50)),
        }
        for variant in VARIANTS:
            out_dir = ROOT / "out" / variant
            out_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_dir / f"{p.stem}.jpg"), edges[variant], [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"done: {len(paths)} x {len(VARIANTS)} variants")


if __name__ == "__main__":
    main()
